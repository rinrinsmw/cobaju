"""Health-check endpoint used to confirm that the API is running."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.database import get_session, verify_database_connection


router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Public response returned by the health endpoint."""

    status: Literal["ok"]


class DatabaseHealthResponse(HealthResponse):
    """Public response returned when the database accepts a query."""

    database: Literal["ok"]


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Return a simple response when the API process is healthy."""

    return HealthResponse(status="ok")


@router.get(
    "/health/database",
    response_model=DatabaseHealthResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Database unavailable",
        }
    },
)
def database_health_check(
    session: Session = Depends(get_session),
) -> DatabaseHealthResponse:
    """Confirm that the API can execute a query through SQLModel."""

    try:
        verify_database_connection(session)
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from error

    return DatabaseHealthResponse(status="ok", database="ok")
