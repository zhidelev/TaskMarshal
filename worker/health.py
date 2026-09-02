from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import uuid4

HEALTH_FILE = Path("/tmp/taskmarshal-worker.ready")
MAX_AGE_SECONDS = 15
logger = logging.getLogger("taskmarshal.worker")


def is_ready(path: Path = HEALTH_FILE) -> bool:
    """Readiness expires if the worker stops confirming Temporal health."""
    try:
        age = time.monotonic() - float(path.read_text())
    except (OSError, ValueError):
        return False
    return 0 <= age < MAX_AGE_SECONDS


async def refresh_readiness(
    check: Callable[[], Awaitable[bool]],
    path: Path = HEALTH_FILE,
    *,
    timeout: float = 5,
) -> bool:
    started = time.monotonic()
    common = {"correlation_id": str(uuid4()), "operation": "worker.readiness"}
    logger.info(json.dumps({**common, "event": "operation.start", "reason_code": "probe.started"}))
    temporary = path.with_suffix(".tmp")
    try:
        healthy = await asyncio.wait_for(check(), timeout=timeout)
        if not healthy:
            raise RuntimeError("Dependency is not serving")
        temporary.write_text(str(time.monotonic()))
        temporary.replace(path)
    except Exception:
        path.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        healthy = False
    logger.info(
        json.dumps(
            {
                **common,
                "event": "operation.success" if healthy else "operation.failure",
                "reason_code": "temporal.connected" if healthy else "worker.readiness_failed",
                "duration_ms": round((time.monotonic() - started) * 1000),
            }
        )
    )
    return healthy


if __name__ == "__main__":
    raise SystemExit(0 if is_ready() else 1)
