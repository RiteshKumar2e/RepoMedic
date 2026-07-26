"""Isolated, disposable workspaces for repository checkouts.

Guarantees enforced here:

* Every clone lands under ``WORKSPACE_ROOT`` — path traversal is rejected.
* Clones are shallow and size-capped.
* Workspaces are deleted when the analysis finishes, and any workspace older
  than ``WORKSPACE_RETENTION_MINUTES`` is swept on startup.
* Repository source is never persisted to the database.
"""

from __future__ import annotations

import fnmatch
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from app.core.config import settings
from app.core.errors import SandboxError, ValidationError
from app.core.logging import get_logger
from app.domain.types import Language, SourceFile

logger = get_logger(__name__)

# Directories never worth reading, parsing or sending anywhere.
DEFAULT_IGNORES = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".next", ".turbo", "coverage", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "vendor", "target", ".idea", ".vscode",
}
MAX_FILE_BYTES = 512_000
BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tar",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".so", ".dll", ".exe",
    ".pyc", ".class", ".jar", ".wasm", ".lock",
}


@dataclass(slots=True)
class Workspace:
    """A checked-out repository on disk."""

    root: Path
    analysis_id: str
    repository_full_name: str

    def resolve(self, relative_path: str) -> Path:
        """Resolve a repository-relative path, refusing to escape the workspace."""
        candidate = (self.root / relative_path).resolve()
        try:
            candidate.relative_to(self.root.resolve())
        except ValueError as exc:
            raise ValidationError(f"Path escapes the workspace: {relative_path}") from exc
        return candidate

    def read(self, relative_path: str) -> str:
        path = self.resolve(relative_path)
        if not path.is_file():
            raise ValidationError(f"Not a file: {relative_path}")
        return path.read_text(encoding="utf-8", errors="replace")

    def write(self, relative_path: str, content: str) -> None:
        path = self.resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def exists(self, relative_path: str) -> bool:
        try:
            return self.resolve(relative_path).exists()
        except ValidationError:
            return False

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
        logger.info("workspace.cleaned", analysis_id=self.analysis_id)


def _run_git(args: list[str], cwd: Optional[Path] = None, timeout: int = 300) -> str:
    """Run a git command with a fixed argv (never a shell string)."""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "echo"},
        )
    except FileNotFoundError as exc:
        raise SandboxError("git is not installed on this host") from exc
    except subprocess.TimeoutExpired as exc:
        raise SandboxError(f"git {args[0]} timed out") from exc

    if completed.returncode != 0:
        raise SandboxError(
            f"git {args[0]} failed", details={"stderr": completed.stderr[-800:]}
        )
    return completed.stdout


def create_workspace(analysis_id: str, repository_full_name: str) -> Workspace:
    root = settings.workspace_path / analysis_id
    root.mkdir(parents=True, exist_ok=True)
    return Workspace(root=root, analysis_id=analysis_id, repository_full_name=repository_full_name)


def clone_pull_request(
    workspace: Workspace,
    clone_url: str,
    *,
    token: str = "",
    base_sha: str = "",
    head_sha: str = "",
    head_ref: str = "",
    depth: int = 50,
) -> None:
    """Shallow-clone the repository and check out the pull-request head."""
    authed_url = clone_url
    if token and clone_url.startswith("https://"):
        # Credential stays in-process; it is never logged (see logging redaction).
        authed_url = clone_url.replace("https://", f"https://x-access-token:{token}@", 1)

    _run_git(["init", "--quiet", str(workspace.root)])
    _run_git(["remote", "add", "origin", authed_url], cwd=workspace.root)

    refs = [ref for ref in (head_sha, base_sha, head_ref) if ref]
    fetched = False
    for ref in refs:
        try:
            _run_git(["fetch", "--depth", str(depth), "origin", ref], cwd=workspace.root)
            fetched = True
        except SandboxError:
            continue
    if not fetched:
        _run_git(["fetch", "--depth", str(depth), "origin"], cwd=workspace.root)

    target = head_sha or head_ref or "FETCH_HEAD"
    _run_git(["checkout", "--quiet", "--force", target], cwd=workspace.root)

    size_mb = directory_size_mb(workspace.root)
    if size_mb > settings.max_repository_size_mb:
        workspace.cleanup()
        raise ValidationError(
            f"Repository exceeds the {settings.max_repository_size_mb} MB analysis limit "
            f"({size_mb:.0f} MB)"
        )
    logger.info(
        "workspace.cloned",
        analysis_id=workspace.analysis_id,
        repository=workspace.repository_full_name,
        size_mb=round(size_mb, 1),
    )


def diff_name_status(workspace: Workspace, base_sha: str, head_sha: str) -> list[tuple[str, str]]:
    """Return ``(status, path)`` pairs between two revisions."""
    try:
        output = _run_git(["diff", "--name-status", f"{base_sha}..{head_sha}"], cwd=workspace.root)
    except SandboxError:
        return []
    pairs: list[tuple[str, str]] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            pairs.append((parts[0][0], parts[-1]))
    return pairs


def unified_diff(workspace: Workspace, base_sha: str, head_sha: str, path: str = "") -> str:
    args = ["diff", "--unified=3", f"{base_sha}..{head_sha}"]
    if path:
        args += ["--", path]
    try:
        return _run_git(args, cwd=workspace.root)
    except SandboxError:
        return ""


def directory_size_mb(path: Path) -> float:
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORES]
        for name in filenames:
            try:
                total += (Path(dirpath) / name).stat().st_size
            except OSError:
                continue
    return total / (1024 * 1024)


def is_excluded(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    for pattern in patterns:
        if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(normalized, f"*/{pattern}"):
            return True
        if pattern.endswith("/**") and normalized.startswith(pattern[:-3] + "/"):
            return True
    return False


def iter_source_files(
    workspace: Workspace,
    *,
    excluded_paths: Optional[list[str]] = None,
    languages: Optional[set[Language]] = None,
    max_files: int = 5000,
) -> Iterator[SourceFile]:
    """Walk the workspace yielding readable, non-binary, non-excluded text files."""
    excluded_paths = excluded_paths or []
    count = 0
    root = workspace.root.resolve()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORES]
        for name in sorted(filenames):
            if count >= max_files:
                return
            absolute = Path(dirpath) / name
            relative = absolute.relative_to(root).as_posix()

            if absolute.suffix.lower() in BINARY_SUFFIXES:
                continue
            if is_excluded(relative, excluded_paths):
                continue
            language = Language.from_path(relative)
            if languages and language not in languages:
                continue
            try:
                size = absolute.stat().st_size
                if size > MAX_FILE_BYTES:
                    continue
                content = absolute.read_text(encoding="utf-8", errors="strict")
            except (OSError, UnicodeDecodeError):
                continue

            count += 1
            yield SourceFile(
                path=relative,
                content=content,
                language=language,
                size_bytes=size,
                is_test=_looks_like_test(relative),
            )


def _looks_like_test(path: str) -> bool:
    lowered = path.lower()
    return (
        "/test" in f"/{lowered}"
        or lowered.startswith("test")
        or "__tests__" in lowered
        or lowered.endswith((".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".spec.tsx", ".spec.js"))
        or (lowered.endswith(".py") and ("test_" in Path(lowered).name or lowered.endswith("_test.py")))
    )


def sweep_stale_workspaces() -> int:
    """Delete workspaces past the retention window. Called on startup and by a task."""
    root = settings.workspace_path
    if not root.exists():
        return 0
    cutoff = time.time() - settings.workspace_retention_minutes * 60
    removed = 0
    for child in root.iterdir():
        try:
            if child.is_dir() and child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    if removed:
        logger.info("workspace.swept", removed=removed)
    return removed
