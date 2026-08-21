from __future__ import annotations

import json
import os
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from .agent import ChatOrchestrator
from .auth import resolve_user
from .config import load_settings
from .data_access import Catalog, ReadOnlyDuckDB
from .plans import get_plan_policy, public_plan_summary
from .schemas import ChatRequest, ChatResponse
from .skills import SKILL_REGISTRY
from .state import ConversationStore


settings = load_settings()
catalog = Catalog(settings.dictionary_path)
database = ReadOnlyDuckDB(settings, catalog)
store = ConversationStore(settings.conversation_db_path)
orchestrator = ChatOrchestrator(settings, catalog, database, store)


class SPAStaticFiles(StaticFiles):
    """Serve the React entry point for client-side routes."""

    async def get_response(self, path: str, scope: dict):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            is_not_found = exc.status_code == 404
            is_client_route = "." not in path.rsplit("/", 1)[-1]

            if is_not_found and is_client_route:
                return await super().get_response("index.html", scope)

            raise


app = FastAPI(title="AI 藝術品拍賣資料查詢 Agent API", version="0.1.0")
frontend_directory = settings.project_root / "frontend" / "dist"
if frontend_directory.exists():
    app.mount("/ui", SPAStaticFiles(directory=frontend_directory, html=True), name="ui")
configured_origins = [
    origin.strip()
    for origin in os.getenv("AUCTION_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.mode == "mock" else configured_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "X-Anonymous-Id", "X-Client-Request-Id"],
)


class ModelSwitchRequest(BaseModel):
    """Runtime model selector for the frontend; it never accepts an API key."""

    model: str = Field(min_length=1, max_length=80)


def _allowed_models() -> list[str]:
    configured = [item.strip() for item in os.getenv("AUCTION_ALLOWED_MODELS", "").split(",") if item.strip()]
    candidates = configured or [settings.openai_model, "gpt-5.5", "gpt-5.5-mini", "luna"]
    return list(dict.fromkeys(candidates))


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "auction-research-api",
        "mode": settings.mode,
        "dataset": {
            "name": "auction_demo",
            "read_only": True,
            "database_exists": settings.db_path.exists(),
            "table_count": len(catalog.tables),
        },
    }


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui/")


@app.get("/api/catalog")
def catalog_endpoint() -> dict:
    """Expose the safe schema for a future frontend or agent UI."""
    return {
        "tables": [
            {"name": table, "columns": sorted(catalog.columns.get(table, ())) }
            for table in sorted(catalog.tables)
        ],
        "database": "auction_demo.duckdb",
        "read_only": True,
        "disclosure": "拍賣市場欄位為模擬資料；故宮欄位保留來源脈絡。",
    }


@app.get("/api/skills")
def skills_endpoint() -> dict:
    return {"skills": [skill.as_dict() for skill in SKILL_REGISTRY]}


@app.get("/api/me")
def me_endpoint(http_request: Request) -> dict:
    """Return the server-resolved plan and today's usage for the caller."""
    user = resolve_user(
        http_request.headers.get("Authorization"),
        http_request.headers.get("X-Anonymous-Id"),
    )
    policy = get_plan_policy(user.plan_id)
    return {
        "user_id": user.user_id,
        "authenticated": user.authenticated,
        "plan": public_plan_summary(policy, store.usage_today(user.user_id)),
    }


@app.get("/api/models")
def models_endpoint() -> dict:
    """Return selectable model ids without exposing credentials."""
    return {"models": _allowed_models(), "current": settings.openai_model}


@app.post("/api/model")
def switch_model(payload: ModelSwitchRequest) -> dict:
    """Switch the in-process model used by subsequent Agent requests."""
    if payload.model not in _allowed_models():
        return {"ok": False, "error": {"code": "MODEL_NOT_ALLOWED", "message": "不在允許的模型清單中。"}, "current": settings.openai_model}
    settings.openai_model = payload.model
    return {"ok": True, "current": settings.openai_model}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, http_request: Request):
    request_id = http_request.headers.get("X-Client-Request-Id") or f"req_{uuid4().hex[:12]}"
    user = resolve_user(
        http_request.headers.get("Authorization"),
        http_request.headers.get("X-Anonymous-Id"),
    )
    if request.stream:
        return StreamingResponse(
            _sse_events(orchestrator.chat_stream(request, request_id, user=user)),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return await orchestrator.chat(request, request_id, user=user)


async def _sse_events(events):
    async for event in events:
        yield f"event: {event['event']}\n"
        yield f"data: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
