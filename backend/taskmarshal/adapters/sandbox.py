from __future__ import annotations

from taskmarshal.domain.models import ExecutionPackage
from taskmarshal.domain.ports import AdapterFailure, SandboxProvider


class DenyByDefaultSandboxProvider(SandboxProvider):
    """Foundation placeholder that fails closed until isolated execution lands in 0.2."""

    async def prepare(self, package: ExecutionPackage) -> str:
        raise AdapterFailure(
            "sandbox.not_configured",
            f"No sandbox provider is configured for attempt {package.attempt_id}.",
        )

    async def destroy(self, sandbox_id: str) -> None:
        return None
