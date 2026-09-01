from __future__ import annotations

import asyncio
import logging
import os

from temporalio.client import Client


async def main() -> None:
    address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    await Client.connect(address)
    logging.info("worker.ready", extra={"reason_code": "temporal.connected"})
    # Execution workflows arrive with isolated sandboxing in milestone 0.2. Keeping a
    # connected worker process here verifies the development dependency and port boundary.
    await asyncio.Event().wait()


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    asyncio.run(main())
