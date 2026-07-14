"""Tests for the public health endpoint."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, create_engine, select

import app.routers.health as health_router
from app.database import get_session
from app.main import app


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    """Give each test a temporary SQLite database."""

    database_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_health_check_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_health_check_returns_ok(client: TestClient) -> None:
    response = client.get("/health/database")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_database_health_check_hides_internal_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_database_error(session: Session) -> None:
        raise OperationalError("SELECT 1", {}, Exception("private database detail"))

    monkeypatch.setattr(
        health_router,
        "verify_database_connection",
        raise_database_error,
    )

    response = client.get("/health/database")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
    assert "private database detail" not in response.text


def test_session_dependency_can_execute_a_query(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'session.db'}")

    with Session(engine) as session:
        result = session.exec(select(1)).one()

    assert result == 1
