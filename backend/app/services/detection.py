"""Project language, framework and dependency detection."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

from app.core.logging import get_logger
from app.domain.types import Language, SourceFile

logger = get_logger(__name__)

FRAMEWORK_MARKERS: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    # (label, dependency names, file markers)
    ("FastAPI", ("fastapi",), ()),
    ("Django", ("django",), ("manage.py",)),
    ("Flask", ("flask",), ()),
    ("SQLAlchemy", ("sqlalchemy", "sqlmodel"), ()),
    ("Celery", ("celery",), ()),
    ("Pydantic", ("pydantic",), ()),
    ("Next.js", ("next",), ("next.config.js", "next.config.mjs", "next.config.ts")),
    ("React", ("react",), ()),
    ("Express", ("express",), ()),
    ("NestJS", ("@nestjs/core",), ()),
    ("Prisma", ("prisma", "@prisma/client"), ("prisma/schema.prisma",)),
    ("Vue", ("vue",), ()),
    ("Svelte", ("svelte",), ()),
    ("Jest", ("jest",), ()),
    ("Vitest", ("vitest",), ()),
    ("pytest", ("pytest",), ("pytest.ini", "conftest.py")),
    ("Tailwind CSS", ("tailwindcss",), ("tailwind.config.js", "tailwind.config.ts")),
    ("Docker", (), ("Dockerfile", "docker-compose.yml")),
]

_REQUIREMENT_RE = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*(?:\[[^\]]*\])?\s*(?:[=<>!~]{1,2}\s*([^\s;#]+))?")


def detect_languages(files: Iterable[SourceFile]) -> dict[str, int]:
    """Line counts per language — the basis for choosing analyzers and scanners."""
    counter: Counter[str] = Counter()
    for source_file in files:
        if source_file.language is Language.UNKNOWN:
            continue
        counter[source_file.language.value] += len(source_file.lines)
    return dict(counter.most_common())


def language_families(languages: dict[str, int]) -> set[str]:
    families: set[str] = set()
    for name in languages:
        try:
            families.add(Language(name).family)
        except ValueError:
            continue
    families.discard("other")
    return families or {"python", "javascript"}


def read_dependencies(workspace_root: Path) -> dict[str, str]:
    """Merge dependencies from package.json and Python requirement files."""
    dependencies: dict[str, str] = {}

    package_json = workspace_root / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            for section in ("dependencies", "devDependencies", "peerDependencies"):
                for name, version in (data.get(section) or {}).items():
                    dependencies[str(name)] = str(version)
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("detection.package_json_unreadable", error=str(exc))

    for filename in ("requirements.txt", "requirements-dev.txt", "pyproject.toml"):
        path = workspace_root / filename
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if filename.endswith(".toml"):
            for match in re.finditer(r'^\s*["\']?([A-Za-z0-9._-]+)["\']?\s*=\s*["\']([^"\']+)["\']', text, re.M):
                dependencies.setdefault(match.group(1).lower(), match.group(2))
            for match in re.finditer(r'^\s*["\']([A-Za-z0-9._-]+)\s*[><=~!]+\s*([^"\']+)["\'],?\s*$', text, re.M):
                dependencies.setdefault(match.group(1).lower(), match.group(2))
        else:
            for line in text.splitlines():
                if not line.strip() or line.lstrip().startswith(("#", "-")):
                    continue
                match = _REQUIREMENT_RE.match(line)
                if match:
                    dependencies.setdefault(match.group(1).lower(), match.group(2) or "*")
    return dependencies


def detect_frameworks(dependencies: dict[str, str], file_paths: set[str]) -> list[str]:
    detected: list[str] = []
    lowered = {name.lower() for name in dependencies}
    for label, dependency_names, markers in FRAMEWORK_MARKERS:
        if any(name.lower() in lowered for name in dependency_names):
            detected.append(label)
        elif any(marker in file_paths for marker in markers):
            detected.append(label)
    return detected


def primary_language(languages: dict[str, int]) -> str:
    return next(iter(languages), "unknown")
