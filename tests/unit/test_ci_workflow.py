from __future__ import annotations

from pathlib import Path

import yaml


def test_ci_runs_fast_checks_and_an_independent_stack_on_pull_requests() -> None:
    workflow = yaml.load(Path(".github/workflows/quality.yml").read_text(), Loader=yaml.BaseLoader)
    assert "pull_request" in workflow["on"]
    assert workflow["permissions"] == {"contents": "read"}
    jobs = workflow["jobs"]
    assert set(jobs) == {"backend-static", "backend-tests", "frontend", "clean-stack"}
    assert "needs" not in jobs["clean-stack"]
    assert jobs["backend-tests"]["strategy"]["fail-fast"] == "false"
    assert {item["suite"] for item in jobs["backend-tests"]["strategy"]["matrix"]["include"]} == {
        "unit",
        "integration",
    }
    integration = next(
        item
        for item in jobs["backend-tests"]["strategy"]["matrix"]["include"]
        if item["suite"] == "integration"
    )
    assert "--postgres-url=" in integration["database_args"]
    assert jobs["backend-tests"]["services"]["postgres"]["image"] == (
        "${{ matrix.suite == 'integration' && 'postgres:17.6-alpine' || '' }}"
    )


def test_ci_uploads_only_successfully_sanitized_reports_with_bounded_retention() -> None:
    workflow = yaml.load(Path(".github/workflows/quality.yml").read_text(), Loader=yaml.BaseLoader)
    for job in workflow["jobs"].values():
        report_steps = [step for step in job["steps"] if step.get("id") == "reports"]
        assert len(report_steps) == 1
        assert "scripts/ci_artifacts.py" in report_steps[0]["run"]
        assert report_steps[0]["if"] == "always()"
        uploads = [
            step for step in job["steps"] if "actions/upload-artifact@" in step.get("uses", "")
        ]
        assert len(uploads) == 1
        assert uploads[0]["if"] == "always() && steps.reports.outcome == 'success'"
        assert uploads[0]["with"]["path"] == "ci-artifacts/"
        assert uploads[0]["with"]["retention-days"] == "7"
        for step in job["steps"]:
            if "uses" in step:
                revision = step["uses"].split("@", 1)[1]
                assert len(revision) == 40 and all(char in "0123456789abcdef" for char in revision)


def test_stack_cleanup_is_unconditional_and_independent_of_report_generation() -> None:
    workflow = yaml.load(Path(".github/workflows/quality.yml").read_text(), Loader=yaml.BaseLoader)
    steps = workflow["jobs"]["clean-stack"]["steps"]
    cleanup = next(step for step in steps if "docker compose down" in step.get("run", ""))
    assert cleanup["if"] == "always()"
    assert "--volumes" in cleanup["run"]
