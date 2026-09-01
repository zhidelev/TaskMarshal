from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Sequence
from pathlib import Path

DOMAIN = Path("backend/taskmarshal/domain")
FORBIDDEN_PREFIXES = (
    "taskmarshal.adapters",
    "taskmarshal.api",
    "taskmarshal.persistence",
    "fastapi",
    "sqlalchemy",
    "alembic",
    "pydantic_ai",
    "temporalio",
    "docker",
    # Git host implementations belong in adapters.
    "github",
    "githubkit",
    "gidgethub",
    "gitlab",
    # Model providers and agent frameworks belong in adapters.
    "openai",
    "anthropic",
    "cohere",
    "groq",
    "mistralai",
    "ollama",
    "google.generativeai",
    "google.genai",
    "vertexai",
    "azure.ai.inference",
    "boto3",
    "botocore",
    "litellm",
    "langchain",
    "crewai",
    "autogen",
)


def imported_modules(tree: ast.AST) -> list[tuple[str, int]]:
    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append((node.module, node.lineno))
    return imports


def is_forbidden(module: str) -> bool:
    matches_forbidden_prefix = (
        module == prefix or module.startswith(f"{prefix}.") for prefix in FORBIDDEN_PREFIXES
    )
    return any(matches_forbidden_prefix)


def find_violations(domain: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(domain.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for module, line in imported_modules(tree):
            if is_forbidden(module):
                violations.append(f"{path}:{line}: prohibited domain dependency {module}")
    return violations


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enforce TaskMarshal dependency direction.")
    parser.add_argument("--domain", type=Path, default=DOMAIN)
    arguments = parser.parse_args(argv)
    violations = find_violations(arguments.domain)
    if violations:
        print("\n".join(violations), file=sys.stderr)
        return 1
    print(
        "Dependency direction valid across "
        f"{len(list(arguments.domain.rglob('*.py')))} domain modules."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
