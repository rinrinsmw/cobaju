"""Health-check endpoint used to confirm that the API is running."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Public response returned by the health endpoint."""

    status: Literal["ok"]


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Return a simple response when the API process is healthy."""

    return HealthResponse(status="ok")
