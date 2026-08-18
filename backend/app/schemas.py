from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ResponseOptions(BaseModel):
    """Backward-compatible per-request overrides; normal callers can omit this."""

    include_sql: bool | None = None
    include_charts: bool | None = None
    include_images: bool | None = None
    include_tables: bool | None = None
    include_trace: bool | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    conversation_id: str | None = Field(default=None, max_length=128)
    mode: Literal["normal", "debug"] = "normal"
    stream: bool = False
    response_options: ResponseOptions = Field(default_factory=ResponseOptions)


class ErrorPayload(BaseModel):
    code: str
    message: str
    retryable: bool = False
    request_id: str | None = None


class ColumnSpec(BaseModel):
    key: str
    label: str
    type: str


class TableResult(BaseModel):
    id: str
    title: str
    columns: list[ColumnSpec]
    rows: list[dict[str, Any]]
    row_count: int


class ChartSpec(BaseModel):
    id: str
    type: Literal["bar", "line", "table", "scatter"]
    title: str
    data_table_id: str
    encoding: dict[str, Any]
    # Self-contained rows let a chart render even when the table block is
    # intentionally hidden by the response policy.
    data: list[dict[str, Any]] = Field(default_factory=list)


class SourceSpec(BaseModel):
    type: str
    table: str | None = None
    description: str
    url: str | None = None


class RepresentativeLot(BaseModel):
    lot_id: str
    title_zh: str
    category: str
    auction_date: str
    image_url: str | None = None


class ImageSpec(BaseModel):
    url: str
    source: str
    source_url: str
    caption: str
    disclosure: str


class TraceStep(BaseModel):
    """User-visible audit event, never hidden chain-of-thought."""

    stage: str
    label: str
    detail: str | None = None
    status: Literal["done", "warning", "blocked"] = "done"


class ContentBlock(BaseModel):
    """Stable renderer contract for the frontend."""

    id: str
    type: Literal["table", "chart", "image", "kpi"]
    title: str
    data: dict[str, Any]


class DebugPayload(BaseModel):
    skills: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[TraceStep] = Field(default_factory=list)
    sql: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    schema_version: str = "1.0"
    conversation_id: str
    answer: str | None = None
    blocks: list[ContentBlock] = Field(default_factory=list)
    debug: DebugPayload | None = None
    sources: list[SourceSpec] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disclosure: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: ErrorPayload | None = None

    # Internal compatibility properties are excluded from the public JSON.
    # Existing backend tests can still inspect the normalized values directly.
    tables: list[TableResult] = Field(default_factory=list, exclude=True)
    charts: list[ChartSpec] = Field(default_factory=list, exclude=True)
    representative_lots: list[RepresentativeLot] = Field(default_factory=list, exclude=True)
    images: list[ImageSpec] = Field(default_factory=list, exclude=True)
    trace: list[TraceStep] = Field(default_factory=list, exclude=True)
    sql: str | None = Field(default=None, exclude=True)
