from __future__ import annotations

import pytest

from taskmarshal.domain.models import ActorResultStatus, AttemptStatus, TaskStatus
from taskmarshal.domain.transitions import (
    InvalidTransition,
    accept_candidate,
    apply_actor_report,
    start_attempt,
)


def test_actor_self_report_never_completes_logical_task() -> None:
    task_status, attempt_status = apply_actor_report(
        TaskStatus.IN_PROGRESS, ActorResultStatus.CANDIDATE_READY
    )

    assert task_status == TaskStatus.AWAITING_REVIEW
    assert attempt_status == AttemptStatus.CANDIDATE
    assert task_status != TaskStatus.COMPLETED


def test_candidate_requires_control_plane_review() -> None:
    with pytest.raises(InvalidTransition):
        accept_candidate(TaskStatus.AWAITING_REVIEW, AttemptStatus.CANDIDATE, False)

    assert accept_candidate(TaskStatus.AWAITING_REVIEW, AttemptStatus.CANDIDATE, True) == (
        TaskStatus.COMPLETED,
        AttemptStatus.ACCEPTED,
    )


def test_start_fails_closed_when_readiness_is_false() -> None:
    with pytest.raises(InvalidTransition, match="readiness"):
        start_attempt(TaskStatus.DRAFT, ready=False)
