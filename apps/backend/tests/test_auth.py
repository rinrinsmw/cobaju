"""API and security tests for Phase 2 authentication."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.config import get_settings
from app.database import get_session
from app.main import app
from app.models.user import User


@pytest.fixture
def client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, Session], None, None]:
    """Give each auth test an isolated database and signing secret."""

    monkeypatch.setenv("JWT_SECRET_KEY", "test-only-secret-with-enough-entropy")
    get_settings.cache_clear()

    engine = create_engine(
        f"sqlite:///{tmp_path / 'auth.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session

    with Session(engine) as inspection_session:
        with TestClient(app) as test_client:
            yield test_client, inspection_session

    app.dependency_overrides.clear()
    get_settings.cache_clear()


def register_user(client: TestClient, email: str = "user@example.com") -> None:
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201


def test_user_can_register_and_password_is_hashed(
    client: tuple[TestClient, Session],
) -> None:
    test_client, session = client

    response = test_client.post(
        "/auth/register",
        json={"email": "New.User@Example.com", "password": "very-secret-password"},
    )

    assert response.status_code == 201
    assert response.json() == {"id": 1, "email": "new.user@example.com"}
    assert "password" not in response.text

    user = session.exec(select(User)).one()
    assert user.email == "new.user@example.com"
    assert user.hashed_password != "very-secret-password"
    assert user.hashed_password.startswith("$argon2")


def test_duplicate_email_is_rejected_case_insensitively(
    client: tuple[TestClient, Session],
) -> None:
    test_client, _ = client
    register_user(test_client, "duplicate@example.com")

    response = test_client.post(
        "/auth/register",
        json={
            "email": "DUPLICATE@example.com",
            "password": "another-secure-password",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "An account with this email already exists"
    }


def test_registration_validates_email_and_password(
    client: tuple[TestClient, Session],
) -> None:
    test_client, _ = client

    invalid_email = test_client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "valid-password"},
    )
    short_password = test_client.post(
        "/auth/register",
        json={"email": "valid@example.com", "password": "short"},
    )

    assert invalid_email.status_code == 422
    assert short_password.status_code == 422


def test_user_can_log_in_and_access_current_user(
    client: tuple[TestClient, Session],
) -> None:
    test_client, _ = client
    register_user(test_client)

    login_response = test_client.post(
        "/auth/login",
        json={
            "email": "USER@example.com",
            "password": "correct-horse-battery-staple",
        },
    )

    assert login_response.status_code == 200
    token_body = login_response.json()
    assert token_body["token_type"] == "bearer"
    assert token_body["access_token"]

    me_response = test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token_body['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json() == {"id": 1, "email": "user@example.com"}


def test_invalid_password_is_rejected(
    client: tuple[TestClient, Session],
) -> None:
    test_client, _ = client
    register_user(test_client)

    response = test_client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect email or password"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer not-a-valid-token"},
        {"Authorization": "Basic not-a-bearer-token"},
    ],
)
def test_protected_endpoint_rejects_unauthenticated_requests(
    client: tuple[TestClient, Session],
    headers: dict[str, str],
) -> None:
    test_client, _ = client

    response = test_client.get("/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
    assert response.headers["www-authenticate"] == "Bearer"
