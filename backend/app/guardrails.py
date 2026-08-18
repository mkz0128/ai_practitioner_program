from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

try:
    import sqlglot
    from sqlglot import exp
except ImportError:  # pragma: no cover - dependency is installed by the backend setup
    sqlglot = None
    exp = None


class GuardrailError(ValueError):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


COLLECTION_HINTS = (
    "拍賣",
    "拍品",
    "收藏",
    "藝術",
    "古董",
    "藏品",
    "成交",
    "流拍",
    "撤拍",
    "估價",
    "拍賣公司",
    "拍賣場次",
    "場次",
    "作者",
    "藝術家",
    "年代",
    "作品",
    "類別",
    "狀態",
    "排名",
    "趨勢",
    "年度",
    "資料集",
    "資料庫",
    "幾筆",
    "筆數",
    "圖片",
    "照片",
    "陶瓷器",
    "銅器",
    "玉器",
    "繪畫",
    "法書",
    "成交率",
    "成交價",
    "成交金額",
    "lot",
)

OFF_SCOPE_HINTS = (
    "天氣",
    "旅遊",
    "新聞",
    "股票",
    "程式教學",
    "寫程式",
    "食譜",
)

INJECTION_HINTS = (
    "ignore previous",
    "ignore all previous",
    "system prompt",
    "developer message",
    "忽略之前",
    "忽略所有規則",
    "顯示 api key",
    "顯示金鑰",
    "洩漏 prompt",
)

META_REQUEST_HINTS = (
    "這個 agent",
    "這個agent",
    "agent 怎麼",
    "agent如何",
    "怎麼做的",
    "如何做到",
    "你的指令",
    "系統提示",
    "system prompt",
    "developer message",
    "api key",
    "金鑰",
    "prompt",
    "skill",
    "guardrail",
    "推理過程",
    "思考過程",
    "內部流程",
)

FORBIDDEN_SQL = re.compile(
    r"\b(drop|delete|update|insert|alter|create|copy|attach|install|load|pragma|call|export|import|read_csv|read_json|read_text|read_blob|parquet_scan|sqlite_scan|postgres_scan|mysql_scan|delta_scan|glob|httpfs|http_get|http_post)\b",
    re.IGNORECASE,
)


def check_user_input(message: str, *, has_context: bool = False) -> None:
    lowered = message.lower()
    if any(marker in lowered for marker in INJECTION_HINTS):
        raise GuardrailError("PROMPT_INJECTION", "這個請求包含不能覆蓋系統規則的指示。")
    if any(marker in lowered for marker in META_REQUEST_HINTS):
        raise GuardrailError(
            "META_OUT_OF_SCOPE",
            "我只協助藝術品拍賣資料查詢；請詢問年份、類別、作者、成交價、排名或拍品圖片。",
            retryable=False,
        )
    if any(marker in lowered for marker in OFF_SCOPE_HINTS) and not any(
        marker in lowered for marker in COLLECTION_HINTS
    ):
        raise GuardrailError(
            "OUT_OF_SCOPE",
            "抱歉，我僅提供藝術品拍賣資料查詢與相關分析。請告訴我想查詢的藝術家、作品類別、年份、價格或拍賣條件。",
        )
    if not has_context and not any(marker in lowered for marker in COLLECTION_HINTS):
        raise GuardrailError(
            "NEED_CLARIFICATION",
            "請告訴我想查詢的藝術品類別、作者、年份、價格或拍賣條件。",
            retryable=True,
        )


@dataclass(frozen=True)
class SqlCatalog:
    tables: frozenset[str]


def validate_sql(
    sql: str,
    catalog: SqlCatalog,
    max_length: int,
    max_rows: int,
    allowed_tables: frozenset[str] | None = None,
) -> str:
    """Allow one bounded DuckDB read query over the known tables only."""
    if not isinstance(sql, str) or not sql.strip():
        raise GuardrailError("SQL_REJECTED", "SQL 不可以是空白。")
    statement = sql.strip()
    if len(statement) > max_length:
        raise GuardrailError("SQL_REJECTED", "SQL 超過長度限制。")
    if ";" in statement or "--" in statement or "/*" in statement:
        raise GuardrailError("SQL_REJECTED", "只允許單一 SQL，且不允許註解或多語句。")
    if FORBIDDEN_SQL.search(statement):
        raise GuardrailError("SQL_REJECTED", "只允許唯讀 SELECT / WITH 查詢。")
    if sqlglot is None or exp is None:
        if not re.match(r"^(select|with)\b", statement, re.IGNORECASE):
            raise GuardrailError("SQL_REJECTED", "只允許 SELECT / WITH 查詢。")
        return _bound_limit(statement, max_rows)

    try:
        parsed = sqlglot.parse(statement, read="duckdb")
    except Exception as exc:  # pragma: no cover - parser-specific error text
        raise GuardrailError("SQL_REJECTED", f"SQL 無法解析：{exc}") from exc
    if len(parsed) != 1:
        raise GuardrailError("SQL_REJECTED", "只允許單一 SQL statement。")

    tree = parsed[0]
    if type(tree).__name__ not in {"Select", "Union", "Intersect", "Except"}:
        raise GuardrailError("SQL_REJECTED", "只允許 SELECT / WITH 查詢。")

    prohibited_nodes = {
        "Alter",
        "Attach",
        "Command",
        "Copy",
        "Create",
        "Delete",
        "Drop",
        "Insert",
        "LoadData",
        "Merge",
        "Pragma",
        "Set",
        "Transaction",
        "Update",
    }
    for node in tree.walk():
        if type(node).__name__ in prohibited_nodes:
            raise GuardrailError("SQL_REJECTED", "SQL 包含禁止的資料修改或外部存取操作。")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        table_name = table.name.lower()
        if table_name not in catalog.tables and table_name not in cte_names:
            raise GuardrailError("SQL_REJECTED", f"不允許查詢資料表：{table.name}")
        if allowed_tables is not None and table_name not in cte_names and table_name not in allowed_tables:
            raise GuardrailError("PLAN_LIMIT_REACHED", "目前方案不支援跨資料表分析。")

    return _bound_limit(statement, max_rows, has_limit=tree.find(exp.Limit) is not None)


def _bound_limit(statement: str, max_rows: int, has_limit: bool = False) -> str:
    limit_match = re.search(r"\blimit\s+(\d+)\b", statement, re.IGNORECASE)
    if limit_match and int(limit_match.group(1)) > max_rows:
        raise GuardrailError("SQL_REJECTED", f"LIMIT 不可超過 {max_rows} 筆。")
    if re.search(r"\boffset\s+\d+\b", statement, re.IGNORECASE) and not limit_match:
        raise GuardrailError("SQL_REJECTED", "OFFSET 必須搭配不超過上限的 LIMIT。")
    if has_limit or limit_match:
        return statement
    return f"{statement} LIMIT {max_rows}"


def validate_result_columns(columns: Iterable[str]) -> None:
    if not columns:
        raise GuardrailError("EMPTY_RESULT", "查詢沒有回傳欄位。", retryable=True)
