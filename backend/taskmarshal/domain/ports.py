from __future__ import annotations

from typing import Protocol, runtime_checkable

from taskmarshal.domain.models import ActorResult, ExecutionPackage


class AdapterFailure(RuntimeError):
    """Typed, fail-closed adapter failure safe for orchestration code."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@runtime_checkable
class AgentAdapter(Protocol):
    async def execute(self, package: ExecutionPackage) -> ActorResult: ...


@runtime_checkable
class SandboxProvider(Protocol):
    async def prepare(self, package: ExecutionPackage) -> str: ...

    async def destroy(self, sandbox_id: str) -> None: ...


@runtime_checkable
class WorkflowEngine(Protocol):
    async def start_attempt(self, package: ExecutionPackage) -> str: ...
