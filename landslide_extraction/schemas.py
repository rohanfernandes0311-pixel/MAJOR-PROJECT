from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


class ExtractionJobCreateResponse(BaseModel):
    job_id: str
    status: str = Field(default="queued")


class ExtractionJobStatusResponse(BaseModel):
    job_id: str
    status: str
    row_count: int = 0
    source_name: str | None = None
    output_csv: str | None = None
    error: str | None = None


@dataclass(slots=True)
class JobRecord:
    job_id: str
    status: str
    source_name: str
    source_path: str
    output_csv: str | None = None
    row_count: int = 0
    error: str | None = None
    inspection: dict[str, Any] | None = None
