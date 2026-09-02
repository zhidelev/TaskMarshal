from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from scripts.ci_artifacts import main, sanitized_coverage, sanitized_events, sanitized_junit


def test_junit_drops_names_parameters_and_captured_sensitive_content(tmp_path: Path) -> None:
    raw, safe = tmp_path / "raw.xml", tmp_path / "safe.xml"
    raw.write_text("""<testsuites><testsuite name="credential-sentinel">
      <properties><property name="token" value="credential-sentinel"/></properties>
      <testcase name="test_prompt[credential-sentinel]" classname="credential-sentinel" time="0.2">
        <failure message="credential-sentinel">credential-sentinel</failure>
        <system-out>credential-sentinel</system-out><system-err>credential-sentinel</system-err>
      </testcase></testsuite></testsuites>""")
    sanitized_junit(raw, safe)
    assert "credential-sentinel" not in safe.read_text()
    suite = ET.parse(safe).getroot().find("testsuite")
    assert suite is not None and suite.get("failures") == "1" and suite.get("tests") == "1"


def test_coverage_preserves_only_numeric_totals(tmp_path: Path) -> None:
    raw, safe = tmp_path / "raw.xml", tmp_path / "safe.json"
    raw.write_text("""<coverage line-rate="0.75" lines-valid="4" lines-covered="3"
        branch-rate="credential-sentinel"><sources><source>credential-sentinel</source></sources>
        <packages><package name="credential-sentinel"/></packages></coverage>""")
    sanitized_coverage(raw, safe)
    assert "credential-sentinel" not in safe.read_text()
    assert json.loads(safe.read_text())["line-rate"] == 0.75


def test_compose_artifacts_retain_correlated_events_without_messages(tmp_path: Path) -> None:
    raw, safe = tmp_path / "raw.log", tmp_path / "safe.json"
    raw.write_text(
        "db | credential-sentinel\napi | "
        '{"event":"request.failure","reason_code":"credential-sentinel",'
        '"message":"credential-sentinel",'
        '"correlation_id":"b52265e5-55e0-43fb-aa41-e3b2d9776c57","duration_ms":3}\n'
        'api | {"event":"credential-sentinel"}\n'
        'api | {"event": []}\n'
        'api | {"event":"request.start","reason_code": {"token":"credential-sentinel"}}\n'
    )
    sanitized_events(raw, safe)
    assert "credential-sentinel" not in safe.read_text()
    events = json.loads(safe.read_text())["events"]
    assert events[0]["correlation_id"] == "b52265e5-55e0-43fb-aa41-e3b2d9776c57"
    assert events[0]["duration_ms"] == 3
    assert events[1]["reason_code"] == "redacted"


def test_metrics_allowlist_environment_and_distinguish_workflow_reruns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CI_JOB_STARTED_AT", "100")
    monkeypatch.setattr("scripts.ci_artifacts.time.time", lambda: 112.5)
    monkeypatch.setenv("CI_JOB_RESULT", "failure")
    monkeypatch.setenv("CI_CACHE_HIT", "false")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    monkeypatch.setenv("GITHUB_TOKEN", "credential-sentinel")
    output = tmp_path / "safe"
    assert main(["--job", "backend-static", "--output", str(output)]) == 0
    metrics = json.loads((output / "job-metrics.json").read_text())
    assert metrics["duration_seconds"] == 12.5
    assert metrics["reason_code"] == "ci.job.failure"
    assert metrics["cache_hit"] is False
    assert metrics["workflow_attempt"] == 2
    assert type(metrics["workflow_attempt"]) is int
    assert metrics["flaky_rerun_count"] == 0
    assert "credential-sentinel" not in json.dumps(metrics)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", 1),
        ("2", 2),
        ("9007199254740993", 9007199254740993),
        (None, None),
        ("", None),
        ("invalid", None),
        ("2.0", None),
        ("1.5", None),
        ("1e2", None),
        ("NaN", None),
        ("Infinity", None),
        ("0", None),
        ("-1", None),
    ],
)
def test_workflow_attempt_serializes_as_integer_or_null(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    value: str | None,
    expected: int | None,
) -> None:
    if value is None:
        monkeypatch.delenv("GITHUB_RUN_ATTEMPT", raising=False)
    else:
        monkeypatch.setenv("GITHUB_RUN_ATTEMPT", value)
    output = tmp_path / "safe"
    assert main(["--job", "backend-static", "--output", str(output)]) == 0
    for payload in ((output / "job-metrics.json").read_text(), capsys.readouterr().out):
        attempt = json.loads(payload)["workflow_attempt"]
        assert attempt == expected
        if expected is not None:
            assert type(attempt) is int


@pytest.mark.parametrize("report", ["<coverage/>", "<invalid/>", "not xml"])
def test_invalid_reports_fail_closed(tmp_path: Path, report: str) -> None:
    raw = tmp_path / "raw.xml"
    raw.write_text(report)
    output = tmp_path / "safe"
    assert main(["--job", "frontend", "--coverage", str(raw), "--output", str(output)]) == 1
    assert not (output / "coverage-summary.json").exists()


def test_preexisting_artifact_directory_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "unrelated-secret.txt").write_text("credential-sentinel")
    with pytest.raises(FileExistsError):
        main(["--job", "backend-static", "--output", str(tmp_path)])


def test_artifact_preparation_fails_closed_for_a_missing_report(tmp_path: Path) -> None:
    output = tmp_path / "safe"
    assert (
        main(
            ["--job", "backend-unit", "--junit", str(tmp_path / "absent"), "--output", str(output)]
        )
        == 1
    )
    assert not (output / "junit.xml").exists()
    assert (
        json.loads((output / "job-metrics.json").read_text())["reason_code"]
        == "ci.report_preparation_failed"
    )
    assert (
        json.loads((output / "job-metrics.json").read_text())["reports"]["junit"]
        == "missing_or_invalid"
    )
