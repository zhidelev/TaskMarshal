from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import pytest
from worker.health import MAX_AGE_SECONDS, is_ready, refresh_readiness


@pytest.mark.parametrize("contents", ["broken", "nan", "inf", "-1", "1e100"])
def test_worker_health_rejects_invalid_or_expired_markers(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "worker.ready"
    assert not is_ready(path)
    path.write_text(contents)
    assert not is_ready(path)


def test_worker_health_expires(tmp_path: Path) -> None:
    path = tmp_path / "worker.ready"
    path.write_text(str(time.monotonic() - MAX_AGE_SECONDS - 1))
    assert not is_ready(path)


def test_worker_readiness_fails_closed_and_recovers(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "worker.ready"

    async def healthy() -> bool:
        return True

    async def unavailable() -> bool:
        raise RuntimeError("sensitive-connection-detail")

    async def not_serving() -> bool:
        return False

    async def stalled() -> bool:
        await asyncio.Event().wait()
        return True

    async def scenario() -> None:
        assert not is_ready(path)
        assert await refresh_readiness(healthy, path)
        assert is_ready(path)
        assert not await refresh_readiness(unavailable, path)
        assert not is_ready(path) and not path.exists()
        assert not await refresh_readiness(not_serving, path)
        assert not await refresh_readiness(stalled, path, timeout=0.01)
        assert await refresh_readiness(healthy, path)
        assert is_ready(path)

    with caplog.at_level(logging.INFO, logger="taskmarshal.worker"):
        asyncio.run(scenario())
    assert "sensitive-connection-detail" not in caplog.text
    events = [json.loads(record.message) for record in caplog.records]
    for start, finish in zip(events[::2], events[1::2], strict=True):
        assert start["correlation_id"] == finish["correlation_id"]
        assert finish["duration_ms"] >= 0
        assert finish["reason_code"] in {"temporal.connected", "worker.readiness_failed"}
