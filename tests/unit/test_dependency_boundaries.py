from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def run_checker(domain: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/check_dependencies.py", "--domain", str(domain)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_repository_domain_has_no_infrastructure_dependencies() -> None:
    result = run_checker(Path("backend/taskmarshal/domain"))

    assert result.returncode == 0
    assert "Dependency direction valid" in result.stdout


@pytest.mark.parametrize(
    "module",
    [
        "taskmarshal.persistence.tables",
        "fastapi",
        "sqlalchemy.orm",
        "temporalio.client",
        "docker",
        "github",
        "githubkit.rest",
        "openai",
        "anthropic.types",
        "google.genai",
        "boto3",
        "pydantic_ai",
    ],
)
def test_checker_rejects_prohibited_domain_imports(tmp_path: Path, module: str) -> None:
    domain = tmp_path / "domain"
    domain.mkdir()
    (domain / "policy.py").write_text(f"import {module}\n")

    result = run_checker(domain)

    assert result.returncode == 1
    assert f"prohibited domain dependency {module}" in result.stderr


@pytest.mark.parametrize(
    ("statement", "resolved_module"),
    [
        ("from google import genai", "google.genai"),
        ("from google import genai as provider", "google.genai"),
        ("from azure.ai import inference", "azure.ai.inference"),
        ("from taskmarshal import persistence", "taskmarshal.persistence"),
        ("from google import *", "google.*"),
        ("from .. import persistence", "taskmarshal.persistence"),
        ("from ..adapters import temporal", "taskmarshal.adapters.temporal"),
        ("from .. import *", "taskmarshal.*"),
    ],
)
def test_checker_reconstructs_nested_from_imports(
    tmp_path: Path, statement: str, resolved_module: str
) -> None:
    domain = tmp_path / "domain"
    domain.mkdir()
    (domain / "policy.py").write_text(f"{statement}\n")

    result = run_checker(domain)

    assert result.returncode == 1
    assert f"prohibited domain dependency {resolved_module}" in result.stderr


def test_checker_matches_module_boundaries_not_similar_names(tmp_path: Path) -> None:
    domain = tmp_path / "domain"
    domain.mkdir()
    (domain / "policy.py").write_text("import dockerish\n")

    assert run_checker(domain).returncode == 0


def test_checker_resolves_relative_imports_in_nested_domain_modules(tmp_path: Path) -> None:
    domain = tmp_path / "domain"
    nested = domain / "policies"
    nested.mkdir(parents=True)
    module = nested / "policy.py"
    module.write_text("from .. import ports\n")
    assert run_checker(domain).returncode == 0
    module.write_text("from ...persistence import tables\n")
    assert run_checker(domain).returncode == 1


def test_checker_fails_closed_if_domain_directory_is_missing(tmp_path: Path) -> None:
    assert run_checker(tmp_path / "absent").returncode == 1
