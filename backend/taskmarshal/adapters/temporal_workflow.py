from __future__ import annotations

from temporalio.client import Client

from taskmarshal.domain.models import ExecutionPackage
from taskmarshal.domain.ports import WorkflowEngine


class TemporalWorkflowEngine(WorkflowEngine):
    def __init__(self, client: Client, task_queue: str = "taskmarshal-attempts") -> None:
        self.client = client
        self.task_queue = task_queue

    async def start_attempt(self, package: ExecutionPackage) -> str:
        handle = await self.client.start_workflow(
            "TaskMarshalAttemptWorkflow",
            {"work_id": str(package.work_id), "attempt_id": str(package.attempt_id)},
            id=f"attempt-{package.attempt_id}",
            task_queue=self.task_queue,
        )
        return str(handle.result_run_id)
