"""Produce allowlisted CI reports; never publish captured logs or assertion values."""

from __future__ import annotations

import argparse
import json
import math
import os
import time
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

JOBS = ("backend-static", "backend-unit", "backend-integration", "frontend", "clean-stack")
EVENTS = {
    "operation.start",
    "operation.success",
    "operation.failure",
    "request.start",
    "request.success",
    "request.failure",
}
REASONS = {
    "operation.started",
    "operation.succeeded",
    "operation.unhandled_failure",
    "request.started",
    "request.succeeded",
    "request.rejected",
    "request.unhandled_failure",
    "probe.started",
    "temporal.connected",
    "worker.readiness_failed",
    "task.not_ready",
    "agent.concurrency_exhausted",
}


def number(value: object) -> float | None:
    if not isinstance(value, str | int | float) or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and result >= 0 else None


def sanitized_junit(source: Path, destination: Path) -> None:
    source_root = ET.parse(source).getroot()
    if source_root.tag not in {"testsuites", "testsuite"}:
        raise ValueError("Invalid JUnit report")
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite", name="sanitized-tests")
    total_time = 0.0
    counts = dict(tests=0, failures=0, errors=0, skipped=0)
    for index, original in enumerate(source_root.iter("testcase"), start=1):
        duration = number(original.get("time")) or 0
        total_time += duration
        counts["tests"] += 1
        # Even test names/parameter IDs can contain secrets. Keep ordinal identifiers only.
        case = ET.SubElement(suite, "testcase", name=f"case-{index}", time=str(duration))
        for tag, count in (("failure", "failures"), ("error", "errors"), ("skipped", "skipped")):
            if original.find(tag) is not None:
                counts[count] += 1
                ET.SubElement(case, tag, message="Diagnostic content omitted by artifact policy.")
                break
    suite.attrib.update({key: str(value) for key, value in counts.items()})
    suite.set("time", str(total_time))
    ET.indent(root)
    ET.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)


def sanitized_coverage(source: Path, destination: Path) -> None:
    root = ET.parse(source).getroot()
    if root.tag != "coverage" or number(root.get("line-rate")) is None:
        raise ValueError("Invalid coverage report")
    # Numeric coverage totals are useful without exposing machine paths or source text.
    summary = {
        key: number(root.get(key))
        for key in (
            "line-rate",
            "branch-rate",
            "lines-covered",
            "lines-valid",
            "branches-covered",
            "branches-valid",
        )
    }
    destination.write_text(json.dumps(summary, indent=2) + "\n")


def sanitized_events(source: Path, destination: Path) -> None:
    retained: list[dict[str, Any]] = []
    discarded = 0
    for line in source.read_text(errors="replace").splitlines():
        try:
            original = json.loads(line[line.index("{") :])
        except ValueError:
            discarded += 1
            continue
        if (
            not isinstance(original, dict)
            or not isinstance(original.get("event"), str)
            or original["event"] not in EVENTS
        ):
            discarded += 1
            continue
        event = {"event": original["event"]}
        reason = original.get("reason_code")
        event["reason_code"] = (
            reason if isinstance(reason, str) and reason in REASONS else "redacted"
        )
        for key in ("work_id", "attempt_id", "correlation_id"):
            value = original.get(key)
            if isinstance(value, str):
                with suppress(ValueError):
                    event[key] = str(UUID(value))
        duration = number(original.get("duration_ms"))
        if duration is not None:
            event["duration_ms"] = duration
        retained.append(event)
    destination.write_text(
        json.dumps({"events": retained, "discarded_lines": discarded}, indent=2) + "\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", choices=JOBS, required=True)
    parser.add_argument("--output", type=Path, default=Path("ci-artifacts"))
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--coverage", type=Path)
    parser.add_argument("--compose", type=Path)
    args = parser.parse_args(argv)
    # A fresh directory prevents stale or unrelated files from reaching the upload step.
    args.output.mkdir(parents=True, exist_ok=False)
    reports: dict[str, str] = {}
    for key, source, destination, sanitize in (
        ("junit", args.junit, "junit.xml", sanitized_junit),
        ("coverage", args.coverage, "coverage-summary.json", sanitized_coverage),
        ("compose", args.compose, "events.json", sanitized_events),
    ):
        if source is not None:
            try:
                sanitize(source, args.output / destination)
            except (OSError, ValueError, ET.ParseError):
                reports[key] = "missing_or_invalid"
            else:
                reports[key] = "sanitized"
    started = number(os.getenv("CI_JOB_STARTED_AT"))
    status = os.getenv("CI_JOB_RESULT", "unknown")
    cache = os.getenv("CI_CACHE_HIT", "")
    report_failed = "missing_or_invalid" in reports.values()
    reason = (
        f"ci.job.{status}" if status in {"success", "failure", "cancelled"} else "ci.job.unknown"
    )
    metrics = {
        "job": args.job,
        "correlation_id": str(uuid4()),
        "reason_code": "ci.report_preparation_failed" if report_failed else reason,
        "duration_seconds": round(max(0, time.time() - started), 3)
        if started is not None
        else None,
        "cache_hit": {"true": True, "false": False}.get(cache),
        "workflow_attempt": number(os.getenv("GITHUB_RUN_ATTEMPT")),
        "flaky_rerun_count": 0,  # No automatic test retries; workflow reruns are separate.
        "reports": reports,
    }
    (args.output / "job-metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics))
    return 1 if report_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
