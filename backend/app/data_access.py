from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from .config import Settings
from .guardrails import GuardrailError, SqlCatalog, validate_result_columns, validate_sql


@dataclass(frozen=True)
class QueryResult:
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool


class Catalog:
    def __init__(self, dictionary_path: Path) -> None:
        tables: set[str] = set()
        columns: dict[str, set[str]] = {}
        column_details: dict[str, list[dict[str, str]]] = {}
        with dictionary_path.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                table = row["table_name"].strip().lower()
                column = row["column_name"].strip().lower()
                tables.add(table)
                columns.setdefault(table, set()).add(column)
                column_details.setdefault(table, []).append(
                    {
                        "name": column,
                        "type": row.get("data_type", "").strip(),
                        "allowed_values": row.get("allowed_values", "").strip(),
                        "description": row.get("description", "").strip(),
                        "null_rule": row.get("null_rule", "").strip(),
                        "key_or_constraint": row.get("key_or_constraint", "").strip(),
                        "references": row.get("references", "").strip(),
                    }
                )
        self.tables = frozenset(tables)
        self.columns = {table: frozenset(values) for table, values in columns.items()}
        self.column_details = column_details
        self.sql_catalog = SqlCatalog(self.tables)

    def agent_payload(self) -> dict[str, list[dict[str, str]]]:
        """Return schema semantics the model needs to write correct SQL literals."""
        return {
            table: self.column_details.get(table, [])
            for table in sorted(self.tables)
        }


class ReadOnlyDuckDB:
    def __init__(self, settings: Settings, catalog: Catalog) -> None:
        self.settings = settings
        self.catalog = catalog
        if not settings.db_path.exists():
            raise FileNotFoundError(f"DuckDB not found: {settings.db_path}")

    def query(
        self,
        sql: str,
        *,
        max_rows: int | None = None,
        allowed_tables: frozenset[str] | None = None,
    ) -> QueryResult:
        effective_max_rows = max_rows or self.settings.max_rows
        bounded_sql = validate_sql(
            sql,
            self.catalog.sql_catalog,
            max_length=self.settings.max_sql_length,
            max_rows=effective_max_rows,
            allowed_tables=allowed_tables,
        )
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._query_sync, bounded_sql, effective_max_rows)
        try:
            result = future.result(timeout=self.settings.query_timeout_seconds)
            executor.shutdown(wait=True)
            return result
        except FutureTimeoutError as exc:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            raise GuardrailError("QUERY_TIMEOUT", "查詢超過時間限制，請縮小範圍。", retryable=True) from exc
        except GuardrailError:
            executor.shutdown(wait=True)
            raise
        except Exception as exc:
            executor.shutdown(wait=True)
            raise GuardrailError("QUERY_ERROR", "查詢無法執行，請檢查條件或稍後再試。", retryable=True) from exc

    def _query_sync(self, sql: str, max_rows: int) -> QueryResult:
        connection = duckdb.connect(str(self.settings.db_path), read_only=True)
        try:
            connection.execute("SET memory_limit='256MB'")
            cursor = connection.execute(sql)
            columns = [description[0] for description in cursor.description or []]
            validate_result_columns(columns)
            raw_rows = cursor.fetchmany(max_rows + 1)
            truncated = len(raw_rows) > max_rows
            rows = [
                {column: _json_value(value) for column, value in zip(columns, row)}
                for row in raw_rows[:max_rows]
            ]
            return QueryResult(sql=sql, columns=columns, rows=rows, truncated=truncated)
        finally:
            connection.close()


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return json.loads(json.dumps(value, default=str))
