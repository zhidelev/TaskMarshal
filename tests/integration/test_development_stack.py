from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(scope="module")
def stack() -> dict[str, Any]:
    if shutil.which("docker") is None:
        pytest.skip("Compose configuration checks require the Docker CLI, not a daemon")
    environment = os.environ.copy()
    for key in (
        "DATABASE_URL",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "VITE_API_URL",
        "COMPOSE_FILE",
        "COMPOSE_PROFILES",
        "COMPOSE_ENV_FILES",
        "LOG_LEVEL",
    ):
        environment.pop(key, None)
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            os.devnull,
            "-f",
            "docker-compose.yml",
            "config",
            "--format",
            "json",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    config: dict[str, Any] = json.loads(result.stdout)
    return config


def test_stack_waits_for_application_readiness(stack: dict[str, Any]) -> None:
    services = stack["services"]
    assert set(services) == {
        "db",
        "temporal",
        "temporal-ui",
        "migrate",
        "api",
        "worker",
        "frontend",
    }
    for name, service in services.items():
        if name != "migrate":
            assert service["healthcheck"]["test"]
            assert not service["healthcheck"].get("disable", False)
    assert services["api"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert services["worker"]["depends_on"]["temporal"]["condition"] == "service_healthy"
    assert services["frontend"]["depends_on"]["api"]["condition"] == "service_healthy"


def test_local_stack_has_loopback_ports_and_no_host_authority(stack: dict[str, Any]) -> None:
    for service in stack["services"].values():
        assert not service.get("privileged", False)
        assert service.get("network_mode") != "host"
        for port in service.get("ports", []):
            assert port["host_ip"] == "127.0.0.1"
        for volume in service.get("volumes", []):
            assert volume["type"] == "volume"  # no checkout, credentials, or Docker socket mounts
        if "image" in service:
            assert ":" in service["image"] and not service["image"].endswith(":latest")
    assert set(stack["volumes"]) == {"postgres-data"}
    assert "local-only" in stack["services"]["db"]["environment"]["POSTGRES_PASSWORD"]
    assert "POSTGRES_PASSWORD" not in stack["services"]["worker"]["environment"]


def test_docker_context_excludes_local_secrets() -> None:
    patterns = Path(".dockerignore").read_text().splitlines()
    assert {".env", ".env.*", ".git", ".venv", "*.db", "*.log"} <= set(patterns)


def test_default_stack_commands_need_no_host_python() -> None:
    result = subprocess.run(
        ["make", "-n", "dev", "smoke"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--wait" in result.stdout
    assert "exec -T" in result.stdout
    assert "uv run" not in result.stdout
