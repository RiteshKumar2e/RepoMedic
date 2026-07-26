"""End-to-end test over the deliberately vulnerable fixture repository.

Covers the flow required by the product spec:

    import fixture repo -> simulated pull request -> run analysis ->
    show findings -> generate fixes -> validate fixes -> approve a patch ->
    create a (simulated) fix pull request

The demo seeder runs the real pipeline — AST rules, scanners, duplicate-logic
detection, knowledge graph, retrieval, the five reviewer agents and template
patch generation — so this asserts on genuinely produced output, not fixtures.
"""

from __future__ import annotations

import pytest


@pytest.mark.e2e
def test_analysis_completed(authed_client, demo_analysis):
    analysis = authed_client.get(f"/api/v1/analyses/{demo_analysis['analysis_id']}").json()

    assert analysis["status"] == "completed"
    assert analysis["progress"] == 100
    assert analysis["files_analyzed"] > 0
    assert "ast_rules" in analysis["scanners_run"]
    assert analysis["reviewers_run"], "no reviewer agent ran"
    assert analysis["summary"], "no review summary was produced"


@pytest.mark.e2e
def test_context_manifest_records_what_was_transmitted(authed_client, demo_analysis):
    """The manifest is the audit trail for data sent to the model."""
    analysis = authed_client.get(f"/api/v1/analyses/{demo_analysis['analysis_id']}").json()
    manifest = analysis["context_manifest"]

    assert manifest["changed_files"], "manifest lists no changed files"
    assert "estimated_tokens" in manifest
    assert manifest["repository_files_indexed"] > 0
    # The fixture README carries a prompt-injection payload.
    assert manifest["injection_flags"] > 0, "firewall did not flag the fixture payload"


@pytest.mark.e2e
def test_expected_vulnerability_classes_are_found(authed_client, demo_analysis):
    findings = authed_client.get(
        f"/api/v1/analyses/{demo_analysis['analysis_id']}/findings"
    ).json()
    assert findings, "analysis produced no findings"

    rules = {f["rule_id"] for f in findings}
    categories = {f["category"] for f in findings}
    severities = {f["severity"] for f in findings}

    # Each of these is planted in backend/fixtures/ecommerce-api-demo.
    assert "python.sql-injection" in rules
    assert "python.blocking-call-in-async" in rules
    assert "python.n-plus-one-query" in rules
    assert "python.path-traversal" in rules
    assert "python.assert-for-authorization" in rules
    assert "python.swallowed-exception" in rules
    assert "duplicate-logic" in rules

    assert "security" in categories
    assert "performance" in categories
    assert "prompt_injection" in categories, "injection payload was not reported as a finding"
    assert "critical" in severities


@pytest.mark.e2e
def test_findings_are_scored_with_an_explainable_breakdown(authed_client, demo_analysis):
    findings = authed_client.get(
        f"/api/v1/analyses/{demo_analysis['analysis_id']}/findings"
    ).json()

    for finding in findings:
        assert 0 <= finding["score"] <= 100
        assert 0 <= finding["confidence"] <= 1
        breakdown = finding["score_breakdown"]
        assert {
            "severity_weight",
            "scanner_confidence",
            "contextual_relevance",
            "reproducibility_factor",
        } <= set(breakdown)

    # Ordering: the API returns findings worst-first.
    scores = [f["score"] for f in findings]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.e2e
def test_findings_are_deduplicated(authed_client, demo_analysis):
    findings = authed_client.get(
        f"/api/v1/analyses/{demo_analysis['analysis_id']}/findings"
    ).json()
    fingerprints = [f["fingerprint"] for f in findings]
    assert len(fingerprints) == len(set(fingerprints)), "duplicate findings were persisted"


@pytest.mark.e2e
def test_patches_generated_and_validated(authed_client, demo_analysis):
    patches = authed_client.get(
        f"/api/v1/analyses/{demo_analysis['analysis_id']}/patches"
    ).json()
    assert len(patches) >= 3, "spec requires at least three findings with suggested fixes"

    validated = [p for p in patches if p["validation_status"] == "passed"]
    assert len(validated) >= 3, "fewer than three patches passed validation"

    for patch in patches:
        assert patch["unified_diff"], "patch has no diff to display"
        assert patch["explanation"], "patch has no explanation"
        assert patch["original_code"] != patch["suggested_code"]
        assert 0 <= patch["confidence"] <= 100
        # Auto-apply must stay off by default.
        assert patch["auto_apply_eligible"] is False


@pytest.mark.e2e
def test_validation_runs_record_each_step(authed_client, demo_analysis):
    patches = authed_client.get(
        f"/api/v1/analyses/{demo_analysis['analysis_id']}/patches"
    ).json()
    detail = authed_client.get(f"/api/v1/patches/{patches[0]['id']}").json()

    runs = detail["validation_runs"]
    assert runs, "no validation run was recorded"
    steps = {step["name"] for step in runs[0]["step_results"]}
    assert "parse" in steps
    assert runs[0]["parser_passed"] is True


@pytest.mark.e2e
def test_approval_workflow_and_fix_pr_dry_run(authed_client, demo_analysis):
    analysis_id = demo_analysis["analysis_id"]
    patches = authed_client.get(f"/api/v1/analyses/{analysis_id}/patches").json()
    target = next(p for p in patches if p["validation_status"] == "passed")

    approved = authed_client.post(f"/api/v1/patches/{target['id']}/approve").json()
    assert approved["status"] == "approved"
    assert approved["approved_at"]
    assert approved["finding"]["status"] == "fix_approved"

    # The demo account has no GitHub credential, so only a dry run is permitted.
    live = authed_client.post(f"/api/v1/analyses/{analysis_id}/create-fix-pr", json={})
    assert live.status_code == 422
    assert "demo account" in live.json()["error"]["message"].lower()

    dry = authed_client.post(
        f"/api/v1/analyses/{analysis_id}/create-fix-pr", json={"dry_run": True}
    ).json()
    assert dry["created"] is False
    assert dry["branch"].startswith("repomedic/fix-pr")
    assert target["id"] in dry["applied_patches"]
    assert dry["dry_run_diff"]


@pytest.mark.e2e
def test_publish_review_dry_run(authed_client, demo_analysis):
    response = authed_client.post(
        f"/api/v1/analyses/{demo_analysis['analysis_id']}/publish-review",
        json={"dry_run": True},
    ).json()

    assert response["posted"] is False
    body = response["dry_run_body"]
    assert "RepoMedic review" in body
    assert "Severity" in body


@pytest.mark.e2e
def test_patch_rejection(authed_client, demo_analysis):
    patches = authed_client.get(
        f"/api/v1/analyses/{demo_analysis['analysis_id']}/patches"
    ).json()
    target = patches[-1]

    rejected = authed_client.post(
        f"/api/v1/patches/{target['id']}/reject", json={"reason": "prefer a manual refactor"}
    ).json()
    assert rejected["status"] == "rejected"
    assert rejected["rejection_reason"] == "prefer a manual refactor"
    assert rejected["finding"]["status"] == "fix_rejected"


@pytest.mark.e2e
def test_knowledge_graph_is_queryable(authed_client, demo_analysis):
    repository_id = demo_analysis["repository"]["id"]
    graph = authed_client.get(f"/api/v1/repositories/{repository_id}/graph").json()

    assert graph["nodes"], "graph has no nodes"
    assert graph["edges"], "graph has no edges"
    node_types = {n["type"] for n in graph["nodes"]}
    assert "file" in node_types
    assert {"function", "route", "class"} & node_types

    # Findings are attached to their file nodes for the UI overlay.
    assert any(n["finding_count"] > 0 for n in graph["nodes"])


@pytest.mark.e2e
def test_impact_path_for_a_finding(authed_client, demo_analysis):
    repository_id = demo_analysis["repository"]["id"]
    findings = authed_client.get(
        f"/api/v1/analyses/{demo_analysis['analysis_id']}/findings"
    ).json()

    response = authed_client.get(
        f"/api/v1/repositories/{repository_id}/graph/impact",
        params={"finding_id": findings[0]["id"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["finding_id"] == findings[0]["id"]
    assert payload["nodes"]


@pytest.mark.e2e
def test_dashboard_and_analytics(authed_client, demo_analysis):
    dashboard = authed_client.get("/api/v1/dashboard").json()
    assert dashboard["repository_count"] >= 1
    assert dashboard["total_findings"] > 0
    assert dashboard["recent_activity"]
    assert len(dashboard["trend"]) == 14

    analytics = authed_client.get(
        f"/api/v1/repositories/{demo_analysis['repository']['id']}/analytics"
    ).json()
    assert analytics["analyses_run"] >= 1
    assert analytics["findings_by_category"]
    assert analytics["riskiest_modules"]
    assert 0 <= analytics["security_posture_score"] <= 100


@pytest.mark.e2e
def test_finding_filters(authed_client, demo_analysis):
    analysis_id = demo_analysis["analysis_id"]

    critical = authed_client.get(
        f"/api/v1/analyses/{analysis_id}/findings", params={"severity": "critical"}
    ).json()
    assert critical
    assert all(f["severity"] == "critical" for f in critical)

    security = authed_client.get(
        f"/api/v1/analyses/{analysis_id}/findings", params={"category": "security"}
    ).json()
    assert all(f["category"] == "security" for f in security)


@pytest.mark.e2e
def test_sse_stream_replays_a_completed_analysis(authed_client, demo_analysis):
    with authed_client.stream(
        "GET", f"/api/v1/analyses/{demo_analysis['analysis_id']}/events"
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    assert "event:" in body
    assert "completed" in body
