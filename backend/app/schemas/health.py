"""Pydantic response schemas for system health diagnostics."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DatabaseHealth(BaseModel):
    """Sanitized database connectivity status."""

    status: Literal["connected", "disconnected"]
    target: str = Field(description="Sanitized database target without credentials.")
    latency_ms: float | None = Field(default=None, ge=0)
    message: str


class HealthResponse(BaseModel):
    """Structured health-check response payload."""

    status: Literal["ok", "degraded"]
    service: str
    environment: str
    version: str
    timestamp: datetime
    database: DatabaseHealth
