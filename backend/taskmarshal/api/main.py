from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from taskmarshal.api.errors import DomainError
from taskmarshal.api.schemas import (
    AgentConfigurationCreate,
    AgentConfigurationView,
    AgentCreate,
    AgentView,
    AttemptView,
    ErrorEnvelope,
    ProjectCreate,
    ProjectView,
    ReadinessView,
    RepositoryCreate,
    RepositoryView,
    TaskCreate,
    TaskDetail,
    TaskSpecificationCreate,
    TaskSpecificationView,
    TaskView,
)
from taskmarshal.api.service import ControlPlaneService
from taskmarshal.persistence.database import get_session


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for key in (
            "operation",
            "work_id",
            "attempt_id",
            "duration_ms",
            "reason_code",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info and record.exc_info[0]:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, separators=(",", ":"))


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
root_logger = logging.getLogger()
root_logger.handlers = [handler]
root_logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(
    title="TaskMarshal Control Plane",
    version="0.1.0",
    description="Versioned logical tasks, deterministic readiness, and manually started attempts.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def service(session: Session = Depends(get_session)) -> ControlPlaneService:
    return ControlPlaneService(session)


@app.exception_handler(DomainError)
async def domain_error_handler(_request: Request, error: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"error": {"code": error.code, "message": error.message, "details": error.details}},
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_request: Request, _error: IntegrityError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "code": "persistence.constraint_violation",
                "message": (
                    "The request conflicts with an existing immutable identity or reference."
                ),
                "details": [],
            }
        },
    )


@app.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"])
def readiness_probe(session: Session = Depends(get_session)) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ready", "database": "available"}


@app.post(
    "/api/v1/projects",
    response_model=ProjectView,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorEnvelope}},
)
def create_project(
    command: ProjectCreate, control_plane: ControlPlaneService = Depends(service)
) -> Any:
    return control_plane.create_project(command)


@app.get("/api/v1/projects", response_model=list[ProjectView])
def list_projects(control_plane: ControlPlaneService = Depends(service)) -> Any:
    return control_plane.list_projects()


@app.post(
    "/api/v1/repositories",
    response_model=RepositoryView,
    status_code=status.HTTP_201_CREATED,
)
def create_repository(
    command: RepositoryCreate, control_plane: ControlPlaneService = Depends(service)
) -> Any:
    return control_plane.create_repository(command)


@app.get("/api/v1/repositories", response_model=list[RepositoryView])
def list_repositories(control_plane: ControlPlaneService = Depends(service)) -> Any:
    return control_plane.list_repositories()


@app.post("/api/v1/agents", response_model=AgentView, status_code=status.HTTP_201_CREATED)
def create_agent(
    command: AgentCreate, control_plane: ControlPlaneService = Depends(service)
) -> Any:
    return control_plane.create_agent(command)


@app.get("/api/v1/agents", response_model=list[AgentView])
def list_agents(control_plane: ControlPlaneService = Depends(service)) -> Any:
    return control_plane.list_agents()


@app.post(
    "/api/v1/agents/{agent_id}/configurations",
    response_model=AgentConfigurationView,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_configuration(
    agent_id: str,
    command: AgentConfigurationCreate,
    control_plane: ControlPlaneService = Depends(service),
) -> Any:
    return control_plane.create_agent_configuration(agent_id, command)


@app.get("/api/v1/agent-configurations", response_model=list[AgentConfigurationView])
def list_agent_configurations(control_plane: ControlPlaneService = Depends(service)) -> Any:
    return control_plane.list_agent_configurations()


@app.post("/api/v1/tasks", response_model=TaskView, status_code=status.HTTP_201_CREATED)
def create_task(command: TaskCreate, control_plane: ControlPlaneService = Depends(service)) -> Any:
    return control_plane.create_task(command)


@app.get("/api/v1/tasks", response_model=list[TaskView])
def list_tasks(control_plane: ControlPlaneService = Depends(service)) -> Any:
    return control_plane.list_tasks()


@app.get("/api/v1/tasks/{work_id}", response_model=TaskDetail)
def get_task(work_id: str, control_plane: ControlPlaneService = Depends(service)) -> Any:
    task = control_plane.get_task(work_id)
    current = next(
        (
            specification
            for specification in task.specifications
            if specification.id == task.current_specification_id
        ),
        None,
    )
    return {
        "task": task,
        "current_specification": current,
        "specification_history": task.specifications,
        "attempts": task.attempts,
    }


@app.post(
    "/api/v1/tasks/{work_id}/specifications",
    response_model=TaskSpecificationView,
    status_code=status.HTTP_201_CREATED,
)
def create_task_specification(
    work_id: str,
    command: TaskSpecificationCreate,
    control_plane: ControlPlaneService = Depends(service),
) -> Any:
    return control_plane.create_task_specification(work_id, command)


@app.get("/api/v1/tasks/{work_id}/readiness", response_model=ReadinessView)
def task_readiness(work_id: str, control_plane: ControlPlaneService = Depends(service)) -> Any:
    return control_plane.readiness(work_id)


@app.post(
    "/api/v1/tasks/{work_id}/attempts",
    response_model=AttemptView,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorEnvelope}},
)
def start_attempt(work_id: str, control_plane: ControlPlaneService = Depends(service)) -> Any:
    return control_plane.start_attempt(work_id)
