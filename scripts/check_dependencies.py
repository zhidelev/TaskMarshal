from __future__ import annotations

import ast
import sys
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
)


def imported_modules(tree: ast.AST) -> list[tuple[str, int]]:
    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append((node.module, node.lineno))
    return imports


def main() -> int:
    violations: list[str] = []
    for path in sorted(DOMAIN.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for module, line in imported_modules(tree):
            if module.startswith(FORBIDDEN_PREFIXES):
                violations.append(f"{path}:{line}: prohibited domain dependency {module}")
    if violations:
        print("\n".join(violations), file=sys.stderr)
        return 1
    print(f"Dependency direction valid across {len(list(DOMAIN.rglob('*.py')))} domain modules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
