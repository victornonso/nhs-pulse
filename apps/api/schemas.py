from datetime import date, datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class Provenance(BaseModel):
    release_id: UUID
    official_publication: datetime | None
    ingested_at: datetime
    official_url: str
    version: int


class Metric(BaseModel):
    label: str
    value: float | None
    unit: str
    period: date | None
    provenance: list[Provenance]
    detail: str | None = None
    href: str | None = None


class Chart(BaseModel):
    title: str
    rows: list[dict[str, Any]]
    x: str
    y: str
    kind: str
    unit: str
    note: str
    second: str | None = None


class Dashboard(BaseModel):
    model_config = ConfigDict(extra="allow")
    screen: str
    period: date | None
    quarter: date | None
    diagnostic_period: date | None
    metrics: list[Metric]
    charts: list[Chart]
    table: list[dict[str, Any]]
    provenance: dict[str, list[Provenance]]
    notes: list[str]
    generation: int
