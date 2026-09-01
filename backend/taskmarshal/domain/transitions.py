from __future__ import annotations

from taskmarshal.domain.models import ActorResultStatus, AttemptStatus, TaskStatus


class InvalidTransition(ValueError):
    pass


def start_attempt(task_status: TaskStatus, ready: bool) -> tuple[TaskStatus, AttemptStatus]:
    if task_status not in {TaskStatus.READY, TaskStatus.IN_PROGRESS} or not ready:
        raise InvalidTransition("task must satisfy readiness before an attempt can start")
    return TaskStatus.IN_PROGRESS, AttemptStatus.RUNNING


def apply_actor_report(
    task_status: TaskStatus, result_status: ActorResultStatus
) -> tuple[TaskStatus, AttemptStatus]:
    if task_status != TaskStatus.IN_PROGRESS:
        raise InvalidTransition("actor result requires an in-progress task")
    if result_status == ActorResultStatus.CANDIDATE_READY:
        # Actor self-report is evidence for review, never authoritative completion.
        return TaskStatus.AWAITING_REVIEW, AttemptStatus.CANDIDATE
    return TaskStatus.IN_PROGRESS, AttemptStatus.BLOCKED


def accept_candidate(
    task_status: TaskStatus, attempt_status: AttemptStatus, reviewer_approved: bool
) -> tuple[TaskStatus, AttemptStatus]:
    if (
        task_status != TaskStatus.AWAITING_REVIEW
        or attempt_status != AttemptStatus.CANDIDATE
        or not reviewer_approved
    ):
        raise InvalidTransition("only an approved candidate can complete a task")
    return TaskStatus.COMPLETED, AttemptStatus.ACCEPTED
