from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temporalio.client import Client

from worker.health import HEALTH_FILE, refresh_readiness


def make_temporal_check(
    address: str, connect: Callable[[str], Awaitable[Client]]
) -> Callable[[], Awaitable[bool]]:
    client: Client | None = None

    async def check_temporal() -> bool:
        nonlocal client
        try:
            if client is None:
                client = await connect(address)
            healthy = bool(await client.service_client.check_health())
        except (asyncio.CancelledError, Exception):
            # wait_for cancels a stalled probe too: do not reuse that client on retry.
            client = None
            raise
        if not healthy:
            client = None
        return healthy

    return check_temporal


async def main() -> None:
    from temporalio.client import Client

    address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    check_temporal = make_temporal_check(address, Client.connect)

    # Execution workflows arrive with isolated sandboxing in milestone 0.2. Keeping a
    # connected worker process here verifies the development dependency and port boundary.
    HEALTH_FILE.unlink(missing_ok=True)
    try:
        while True:
            await refresh_readiness(check_temporal)
            await asyncio.sleep(3)
    finally:
        HEALTH_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
    asyncio.run(main())
