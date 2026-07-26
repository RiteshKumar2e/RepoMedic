"""Sandboxed command execution for every external tool.

Security model
--------------
* **Allowlist only.** Executables not in :data:`ALLOWED_EXECUTABLES` are refused.
* **No shell.** Commands are argv lists; user/repository input never reaches a shell.
* **Timeouts** on every invocation, plus CPU/memory caps in Docker mode.
* **Network disabled** by default (``--network none``) so a hostile repository
  cannot exfiltrate anything from a scanner or test run.
* Executing *repository* code (test suites) on the host is refused unless
  ``ALLOW_HOST_TEST_EXECUTION=true``; the supported path is Docker mode.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.core.config import SandboxMode, settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Only these binaries may ever be spawned.
ALLOWED_EXECUTABLES = {
    "git", "python", "python3", "ruff", "bandit", "mypy", "radon", "semgrep",
    "pytest", "node", "npm", "npx", "pnpm", "yarn", "eslint", "tsc", "vitest",
    "jest", "gitleaks", "trivy", "osv-scanner", "docker",
}

# Tools that execute repository-authored code and therefore require a sandbox.
CODE_EXECUTING_TOOLS = {"pytest", "vitest", "jest", "npm", "pnpm", "yarn", "node", "python", "python3"}


@dataclass(slots=True)
class CommandResult:
    command: list[str] = field(default_factory=list)
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    duration: float = 0.0
    timed_out: bool = False
    available: bool = True
    skipped_reason: str = ""

    @property
    def ok(self) -> bool:
        return self.available and not self.timed_out and self.returncode == 0


@lru_cache(maxsize=64)
def tool_available(executable: str) -> bool:
    """Whether a tool can actually run in the current sandbox mode."""
    if executable not in ALLOWED_EXECUTABLES:
        return False
    if settings.sandbox_mode is SandboxMode.DISABLED:
        return False
    if settings.sandbox_mode is SandboxMode.DOCKER:
        return shutil.which("docker") is not None
    return shutil.which(executable) is not None


def reset_availability_cache() -> None:
    tool_available.cache_clear()


def _docker_command(argv: Sequence[str], cwd: Path, allow_network: bool, writable: bool) -> list[str]:
    mount = f"{cwd.resolve()}:/workspace:{'rw' if writable else 'ro'}"
    command = [
        "docker", "run", "--rm",
        "--network", "bridge" if allow_network else "none",
        "--cpus", settings.sandbox_cpu_limit,
        "--memory", settings.sandbox_memory_limit,
        "--pids-limit", "256",
        "--security-opt", "no-new-privileges",
        "--cap-drop", "ALL",
        "-v", mount,
        "-w", "/workspace",
        settings.sandbox_image,
        *argv,
    ]
    return command


def run_tool(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout: int | None = None,
    allow_network: bool = False,
    writable: bool = False,
    executes_repository_code: bool = False,
) -> CommandResult:
    """Execute an allowlisted tool and capture its output."""
    argv = list(argv)
    if not argv:
        return CommandResult(available=False, skipped_reason="empty command")

    executable = Path(argv[0]).name
    if executable not in ALLOWED_EXECUTABLES:
        logger.warning("sandbox.blocked_executable", executable=executable)
        return CommandResult(
            command=argv, available=False, skipped_reason=f"{executable} is not allowlisted"
        )

    if settings.sandbox_mode is SandboxMode.DISABLED:
        return CommandResult(command=argv, available=False, skipped_reason="sandbox disabled")

    runs_repo_code = executes_repository_code or executable in CODE_EXECUTING_TOOLS
    if (
        runs_repo_code
        and settings.sandbox_mode is SandboxMode.SUBPROCESS
        and not settings.allow_host_test_execution
    ):
        return CommandResult(
            command=argv,
            available=False,
            skipped_reason=(
                "Refusing to execute repository code on the host. "
                "Set SANDBOX_MODE=docker (recommended) or ALLOW_HOST_TEST_EXECUTION=true."
            ),
        )

    if not tool_available(executable):
        return CommandResult(
            command=argv, available=False, skipped_reason=f"{executable} is not installed"
        )

    command = (
        _docker_command(argv, cwd, allow_network, writable)
        if settings.sandbox_mode is SandboxMode.DOCKER
        else argv
    )
    limit = timeout or settings.scanner_timeout_seconds
    env = _sanitised_env(allow_network)

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=limit,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            command=command,
            returncode=124,
            timed_out=True,
            duration=time.perf_counter() - started,
            skipped_reason=f"timed out after {limit}s",
        )
    except (FileNotFoundError, PermissionError) as exc:
        return CommandResult(command=command, available=False, skipped_reason=str(exc))

    duration = time.perf_counter() - started
    logger.debug(
        "sandbox.tool_finished",
        tool=executable,
        returncode=completed.returncode,
        duration=round(duration, 2),
    )
    return CommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        duration=duration,
    )


def _sanitised_env(allow_network: bool) -> dict[str, str]:
    """Strip credentials from the environment handed to external tools."""
    blocked_prefixes = ("GITHUB_", "ANTHROPIC_", "OPENAI_", "GROQ_", "DATABASE_", "REDIS_")
    blocked_exact = {"JWT_SECRET", "ENCRYPTION_KEY", "AWS_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID"}
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(blocked_prefixes) and key not in blocked_exact
    }
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["NO_COLOR"] = "1"
    env["CI"] = "1"
    if not allow_network:
        # Best-effort for subprocess mode; Docker mode enforces this at the network layer.
        env["HTTP_PROXY"] = env["HTTPS_PROXY"] = "http://127.0.0.1:9"
        env["NO_PROXY"] = ""
    return env
