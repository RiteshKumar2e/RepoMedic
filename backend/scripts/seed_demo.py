"""Seed (or re-seed) the demo workspace.

Runs the real analysis pipeline over `fixtures/ecommerce-api-demo`, so the
dashboard is populated without needing a GitHub account.

    python scripts/seed_demo.py            # seed if not already present
    python scripts/seed_demo.py --force    # discard and rebuild the analysis
    python scripts/seed_demo.py --reset    # delete the demo repository entirely
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging import configure_logging
from app.db.session import init_db, session_scope


async def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the RepoMedic demo workspace")
    parser.add_argument("--force", action="store_true", help="rebuild the demo analysis")
    parser.add_argument("--reset", action="store_true", help="delete the demo repository")
    args = parser.parse_args()

    configure_logging()
    init_db()

    from app.services.demo import reset_demo, seed_demo_workspace

    if args.reset:
        with session_scope() as session:
            reset_demo(session)
        print("Demo repository deleted.")
        return 0

    analysis_id = await seed_demo_workspace(force=args.force)
    if analysis_id is None:
        print("Demo fixture is missing; nothing was seeded.", file=sys.stderr)
        return 1

    from sqlmodel import select

    from app.models.entities import Finding, Patch

    with session_scope() as session:
        findings = list(session.exec(select(Finding).where(Finding.analysis_id == analysis_id)))
        patches = list(
            session.exec(select(Patch).where(Patch.finding_id.in_([f.id for f in findings])))
        )

    print(f"Seeded analysis {analysis_id}")
    print(f"  findings: {len(findings)}")
    print(f"  patches:  {len(patches)}")
    for finding in sorted(findings, key=lambda f: f.score, reverse=True)[:10]:
        print(f"    [{finding.severity.value:<13}] {finding.file_path}:{finding.start_line} — {finding.title[:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
