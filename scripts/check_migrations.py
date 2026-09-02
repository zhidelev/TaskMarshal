from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> None:
    # Never migrate a developer's database just to validate migration history.
    with TemporaryDirectory(prefix="taskmarshal-migrations-") as directory:
        environment = {**os.environ, "DATABASE_URL": f"sqlite:///{Path(directory) / 'check.db'}"}
        for arguments in (
            ("upgrade", "head"),
            ("check",),
            ("downgrade", "base"),
            ("upgrade", "head"),
            ("check",),
        ):
            subprocess.run(
                [sys.executable, "-m", "alembic", *arguments],
                env=environment,
                check=True,
            )


if __name__ == "__main__":
    main()
