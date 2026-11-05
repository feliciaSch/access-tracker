"""Shapes of the JSON going in and out of the API. Pydantic validates incoming data automatically."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["pending", "approved", "denied"]
AccessLevel = Literal["read", "write", "admin"]


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    username: str
    role: str


class RequestCreate(BaseModel):
    resource: str = Field(min_length=1, max_length=128)
    access_level: AccessLevel
    justification: str = Field(min_length=5, max_length=2000)


class StatusUpdate(BaseModel):
    status: Status
    note: str | None = Field(default=None, max_length=500)


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    requester: str
    resource: str
    access_level: str
    justification: str
    status: str
    created_at: datetime
    updated_at: datetime


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    action: str
    old_status: str | None
    new_status: str
    actor: str
    note: str | None
    created_at: datetime
