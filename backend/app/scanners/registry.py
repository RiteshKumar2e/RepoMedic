"""Scanner registry and parallel execution."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from app.core.logging import get_logger
from app.scanners.base import Scanner, ScanRequest, ScanResult
from app.scanners.custom_rules import CustomRuleScanner
from app.scanners.js_scanners import ESLintScanner, NpmAuditScanner, TypeScriptScanner
from app.scanners.python_scanners import BanditScanner, MypyScanner, RadonScanner, RuffScanner
from app.scanners.security_scanners import (
    BuiltinSecretScanner,
    GitleaksScanner,
    OSVScanner,
    PromptInjectionScanner,
    SemgrepScanner,
    TrivyScanner,
)

logger = get_logger(__name__)

# Ordered so the cheapest, always-available scanners report first.
SCANNERS: dict[str, Scanner] = {
    scanner.name: scanner
    for scanner in (
        BuiltinSecretScanner(),
        PromptInjectionScanner(),
        RuffScanner(),
        BanditScanner(),
        MypyScanner(),
        RadonScanner(),
        ESLintScanner(),
        TypeScriptScanner(),
        SemgrepScanner(),
        GitleaksScanner(),
        OSVScanner(),
        NpmAuditScanner(),
        TrivyScanner(),
    )
}

# Scanners that never depend on external binaries — they always contribute.
ALWAYS_ON = {"builtin_secrets", "prompt_injection"}


def available_scanners() -> dict[str, bool]:
    """Map scanner name → whether it can run right now (used by /health and the UI)."""
    return {name: scanner.available() for name, scanner in SCANNERS.items()}


def _select(enabled: list[str] | None, families: set[str]) -> list[Scanner]:
    selected: list[Scanner] = []
    for name, scanner in SCANNERS.items():
        if enabled is not None and name not in enabled and name not in ALWAYS_ON:
            continue
        if scanner.families != {"any"} and not (scanner.families & families):
            continue
        selected.append(scanner)
    return selected


def run_scanners(
    request: ScanRequest,
    *,
    enabled: list[str] | None = None,
    families: set[str] | None = None,
    custom_rules: list[dict] | None = None,
    max_workers: int = 4,
    on_result=None,
) -> list[ScanResult]:
    """Run every applicable scanner, isolating failures to a single scanner."""
    families = families or {"python", "javascript"}
    scanners = _select(enabled, families)
    if custom_rules:
        scanners.append(CustomRuleScanner(custom_rules))

    results: list[ScanResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_safe_scan, scanner, request): scanner for scanner in scanners}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if on_result:
                try:
                    on_result(result)
                except Exception:  # progress callbacks must never fail the run
                    logger.warning("scanner.progress_callback_failed", scanner=result.scanner)

    results.sort(key=lambda r: r.scanner)
    logger.info(
        "scanners.completed",
        ran=[r.scanner for r in results if r.ran],
        skipped=[r.scanner for r in results if not r.ran],
        findings=sum(len(r.findings) for r in results),
    )
    return results


def _safe_scan(scanner: Scanner, request: ScanRequest) -> ScanResult:
    try:
        return scanner.scan(request)
    except Exception as exc:  # a broken tool must not abort the analysis
        logger.warning("scanner.failed", scanner=scanner.name, error=str(exc))
        return ScanResult(scanner.name, ran=False, skipped_reason=f"scanner error: {exc}", raw_error=str(exc))
