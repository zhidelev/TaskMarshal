from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from worker.main import make_temporal_check


@pytest.mark.parametrize("failure", [RuntimeError("Unavailable"), False])
def test_worker_reconnects_after_failed_health_probe(failure: object) -> None:
    first_health = AsyncMock(side_effect=[True, failure])
    second_health = AsyncMock(return_value=True)
    clients = [
        SimpleNamespace(service_client=SimpleNamespace(check_health=health))
        for health in (first_health, second_health)
    ]
    connect = AsyncMock(side_effect=clients)
    check = make_temporal_check("temporal:7233", connect)

    async def scenario() -> None:
        assert await check()
        assert connect.await_count == 1
        if isinstance(failure, Exception):
            with pytest.raises(RuntimeError):
                await check()
        else:
            assert not await check()
        assert connect.await_count == 1  # healthy client was reused before it failed
        assert await check()
        assert connect.await_count == 2
        second_health.assert_awaited_once()

    asyncio.run(scenario())


def test_worker_reconnects_after_a_timed_out_probe() -> None:
    async def stalled() -> bool:
        await asyncio.Event().wait()
        return True

    connect = AsyncMock(
        side_effect=[
            SimpleNamespace(service_client=SimpleNamespace(check_health=stalled)),
            SimpleNamespace(
                service_client=SimpleNamespace(check_health=AsyncMock(return_value=True))
            ),
        ]
    )
    check = make_temporal_check("temporal:7233", connect)

    async def scenario() -> None:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(check(), timeout=0.01)
        assert await check()
        assert connect.await_count == 2

    asyncio.run(scenario())
