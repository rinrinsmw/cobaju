"""Typed request and response bodies for authentication endpoints."""

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    """Information required to create an account."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, email: EmailStr) -> str:
        """Use one lowercase representation for lookup and uniqueness."""

        return str(email).lower()


class UserRead(BaseModel):
    """Safe user information that may be returned by the API."""

    id: int
    email: EmailStr


class LoginRequest(BaseModel):
    """Credentials accepted by the login endpoint."""

    email: EmailStr
    password: str

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, email: EmailStr) -> str:
        return str(email).lower()


class AccessToken(BaseModel):
    """Bearer token returned after successful authentication."""

    access_token: str
    token_type: str = "bearer"
