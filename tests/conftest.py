from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from taskmarshal.api.main import app
from taskmarshal.persistence.database import get_session, make_engine


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--postgres-url",
        default=None,
        help="Postgres test server; each test creates and drops only its own UUID-named schema.",
    )


@pytest.fixture(params=["sqlite", "postgresql"])
def isolated_database_url(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[str]:
    if request.param == "sqlite":
        yield f"sqlite:///{tmp_path / 'test.db'}"
        return
    postgres_url = request.config.getoption("--postgres-url")
    if postgres_url is None:
        pytest.skip("Postgres checks require --postgres-url (enabled in integration CI)")
    schema = f"test_{uuid4().hex}"
    admin_engine = create_engine(postgres_url)
    try:
        with admin_engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        try:
            yield (
                make_url(postgres_url)
                .update_query_dict({"options": f"-csearch_path={schema}"})
                .render_as_string(hide_password=False)
            )
        finally:
            with admin_engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
    finally:
        admin_engine.dispose()


@pytest.fixture
def migration_config(isolated_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Config:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = Config("alembic.ini")
    config.attributes["configure_logger"] = False
    config.set_main_option("sqlalchemy.url", isolated_database_url.replace("%", "%%"))
    return config


@pytest.fixture
def session_factory(
    migration_config: Config, isolated_database_url: str
) -> Iterator[sessionmaker[Session]]:
    # Use deployed DDL (including triggers), not an approximation from Base.metadata.create_all().
    command.upgrade(migration_config, "head")
    engine = make_engine(isolated_database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
