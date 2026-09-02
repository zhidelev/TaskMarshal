from __future__ import annotations

import asyncio
import logging
import os

from temporalio.client import Client

from worker.health import HEALTH_FILE, refresh_readiness


async def main() -> None:
    address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    client: Client | None = None

    async def check_temporal() -> bool:
        nonlocal client
        if client is None:
            client = await Client.connect(address)
        return bool(await client.service_client.check_health())

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
