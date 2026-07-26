"""Finding deduplication and merging.

Multiple tools legitimately detect the same defect — Bandit, Semgrep, an AST
rule and the security reviewer can all flag one SQL injection. Reporting it four
times destroys trust in the tool. Merging them into one finding with three
corroborating sources *increases* confidence instead.
"""

from __future__ import annotations

from collections import defaultdict

from app.core.logging import get_logger
from app.domain.types import UnifiedFinding
from app.retrieval.embeddings import jaccard_similarity

logger = get_logger(__name__)

LINE_PROXIMITY = 4
TITLE_SIMILARITY_THRESHOLD = 0.55


def merge_findings(findings: list[UnifiedFinding]) -> list[UnifiedFinding]:
    """Collapse duplicates, keeping the most informative representative."""
    if not findings:
        return []

    # Group by (file, category) so unrelated categories never merge.
    buckets: dict[tuple[str, str], list[UnifiedFinding]] = defaultdict(list)
    for finding in findings:
        buckets[(finding.file_path, finding.category.value)].append(finding)

    merged: list[UnifiedFinding] = []
    duplicates = 0

    for group in buckets.values():
        group.sort(key=lambda f: (f.start_line, -f.severity.rank))
        clusters: list[list[UnifiedFinding]] = []
        for finding in group:
            target = next(
                (cluster for cluster in clusters if _same_issue(cluster[0], finding)), None
            )
            if target is None:
                clusters.append([finding])
            else:
                target.append(finding)
                duplicates += 1

        for cluster in clusters:
            merged.append(_merge_cluster(cluster))

    if duplicates:
        logger.info("dedupe.merged", duplicates=duplicates, remaining=len(merged))
    return merged


def _same_issue(a: UnifiedFinding, b: UnifiedFinding) -> bool:
    if a.fingerprint == b.fingerprint:
        return True
    if not _lines_overlap(a, b):
        return False
    # Same normalized rule → same issue regardless of wording.
    if a.rule_id and b.rule_id and _normalise_rule(a.rule_id) == _normalise_rule(b.rule_id):
        return True
    if a.cwe and b.cwe and a.cwe == b.cwe:
        return True
    return jaccard_similarity(a.title, b.title) >= TITLE_SIMILARITY_THRESHOLD


def _lines_overlap(a: UnifiedFinding, b: UnifiedFinding) -> bool:
    return (
        a.start_line - LINE_PROXIMITY <= b.end_line
        and b.start_line - LINE_PROXIMITY <= a.end_line
    )


def _normalise_rule(rule_id: str) -> str:
    tail = rule_id.replace("_", "-").rsplit(".", 1)[-1].rsplit("/", 1)[-1].lower()
    aliases = {
        "sql-injection": "sqli",
        "sqli": "sqli",
        "b608": "sqli",
        "s608": "sqli",
        "hardcoded-password-string": "hardcoded-secret",
        "b105": "hardcoded-secret",
        "b106": "hardcoded-secret",
        "s105": "hardcoded-secret",
        "s106": "hardcoded-secret",
        "hardcoded-credential-comparison": "hardcoded-secret",
        "b301": "unsafe-deserialization",
        "s301": "unsafe-deserialization",
        "b307": "dynamic-code-execution",
        "s307": "dynamic-code-execution",
        "dynamic-code-execution": "dynamic-code-execution",
        "no-eval": "dynamic-code-execution",
        "path-traversal": "path-traversal",
        "b108": "path-traversal",
        "ssrf": "ssrf",
        "xss-inner-html": "xss",
        "react-no-danger": "xss",
    }
    return aliases.get(tail, tail)


def _merge_cluster(cluster: list[UnifiedFinding]) -> UnifiedFinding:
    """Pick the best representative and fold in the others' evidence."""
    if len(cluster) == 1:
        return cluster[0]

    # Prefer the richest description at the highest severity.
    primary = max(
        cluster,
        key=lambda f: (
            f.severity.rank,
            len(f.description),
            0 if f.source.is_ai else 1,  # deterministic tools win ties
        ),
    )

    sources: list[str] = []
    for finding in cluster:
        if finding is primary:
            continue
        if finding.source.value not in sources:
            sources.append(finding.source.value)

    primary.corroborating_sources = sorted(set(primary.corroborating_sources) | set(sources))

    # Independent corroboration raises confidence, with diminishing returns.
    base = primary.confidence or primary.source.base_confidence
    boost = 1 - (1 - base) * (0.65 ** len(sources))
    primary.confidence = round(min(0.99, boost), 3)

    # Widen the range to the union so the UI highlights the whole region.
    primary.start_line = min(f.start_line for f in cluster)
    primary.end_line = max(f.end_line for f in cluster)

    # Keep the best fix suggestion available in the cluster.
    if primary.suggested_patch is None:
        primary.suggested_patch = next((f.suggested_patch for f in cluster if f.suggested_patch), None)

    related = {p for f in cluster for p in f.related_files}
    primary.related_files = sorted(related)[:8]
    primary.metadata.setdefault("merged_from", [f.source.value for f in cluster])
    return primary
