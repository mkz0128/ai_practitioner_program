from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseModel):
    """Runtime settings; all paths remain inside the project directory by default."""

    project_root: Path = PROJECT_ROOT
    db_path: Path = PROJECT_ROOT / "data" / "auction_demo.duckdb"
    dictionary_path: Path = PROJECT_ROOT / "data" / "exports" / "data_dictionary.csv"
    conversation_db_path: Path = PROJECT_ROOT / "backend" / "state" / "conversations.sqlite"
    mode: str = Field(default="openai", pattern="^(mock|openai)$")
    # 問答預設使用成本較低的模型；可用 OPENAI_MODEL 覆寫。
    # 目前先以 gpt-5.5 作為保守預設，若帳號提供 Luna API model id，
    # 可直接改成該 model id，不需要改程式碼。
    openai_model: str = "gpt-5.5"
    max_rows: int = Field(default=500, ge=1, le=10_000)
    max_sql_length: int = Field(default=20_000, ge=500, le=100_000)
    query_timeout_seconds: float = Field(default=5.0, gt=0, le=60)


def load_settings() -> Settings:
    _load_project_local_api_key()
    mode = os.getenv("AUCTION_AGENT_MODE", "openai").lower().strip()
    model = os.getenv("OPENAI_MODEL", "gpt-5.5").strip() or "gpt-5.5"
    return Settings(
        db_path=Path(os.getenv("AUCTION_DB_PATH", str(PROJECT_ROOT / "data" / "auction_demo.duckdb"))),
        dictionary_path=Path(
            os.getenv(
                "AUCTION_DICTIONARY_PATH",
                str(PROJECT_ROOT / "data" / "exports" / "data_dictionary.csv"),
            )
        ),
        conversation_db_path=Path(
            os.getenv(
                "AUCTION_CONVERSATION_DB_PATH",
                str(PROJECT_ROOT / "backend" / "state" / "conversations.sqlite"),
            )
        ),
        mode=mode,
        openai_model=model,
        max_rows=int(os.getenv("AUCTION_MAX_ROWS", "500")),
        max_sql_length=int(os.getenv("AUCTION_MAX_SQL_LENGTH", "20000")),
        query_timeout_seconds=float(os.getenv("AUCTION_QUERY_TIMEOUT", "5")),
    )


def _load_project_local_api_key() -> None:
    """Load a local development key without printing or persisting it elsewhere."""
    if os.getenv("OPENAI_API_KEY", "").strip():
        return
    secret_path = os.getenv("OPENAI_API_KEY_FILE", "").strip()
    if secret_path:
        secret_file = Path(secret_path)
        if secret_file.exists():
            key = secret_file.read_text(encoding="utf-8").strip()
            if key:
                os.environ["OPENAI_API_KEY"] = key
                return
    key_path = PROJECT_ROOT / "key.txt"
    if not key_path.exists():
        return
    key = key_path.read_text(encoding="utf-8").strip()
    if key:
        os.environ["OPENAI_API_KEY"] = key
