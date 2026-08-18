from __future__ import annotations

import asyncio
import json
import os
import re
import site
from collections.abc import AsyncIterator, Callable
from uuid import uuid4

from .analysis import QueryIntent, build_sql, classify
from .auth import UserContext
from .config import Settings
from .data_access import Catalog, QueryResult, ReadOnlyDuckDB
from .guardrails import GuardrailError, check_user_input
from .plans import get_plan_policy, PlanPolicy
from .schemas import (
    ChartSpec,
    ChatRequest,
    ChatResponse,
    ColumnSpec,
    DebugPayload,
    ErrorPayload,
    ImageSpec,
    RepresentativeLot,
    SourceSpec,
    TableResult,
    TraceStep,
)
from .skills import choose_skills, skill_instructions
from .response_policy import build_blocks, choose_presentation
from .state import ConversationStore


DISCLOSURE = "拍賣公司、場次、價格與成交狀態為模擬資料，不代表真實拍賣行情或投資建議。"
TraceSink = Callable[[TraceStep], None]


class ChatOrchestrator:
    def __init__(
        self,
        settings: Settings,
        catalog: Catalog,
        database: ReadOnlyDuckDB,
        store: ConversationStore,
    ) -> None:
        self.settings = settings
        self.catalog = catalog
        self.database = database
        self.store = store

    async def chat(
        self,
        request: ChatRequest,
        request_id: str,
        trace_sink: TraceSink | None = None,
        user: UserContext | None = None,
    ) -> ChatResponse:
        conversation_id = request.conversation_id or f"conv_{uuid4().hex[:12]}"
        user_context = user or UserContext(user_id="guest:anonymous", plan_id="guest", authenticated=False)
        plan = get_plan_policy(user_context.plan_id)
        try:
            previous_messages = self.store.history(conversation_id, limit=plan.history_messages)
            check_user_input(request.message, has_context=bool(previous_messages))
            allowed, used_today = self.store.consume_usage(user_context.user_id, plan.daily_questions)
            if not allowed:
                raise GuardrailError(
                    "PLAN_LIMIT_REACHED",
                    f"{plan.label}今日問答額度已用完，請明天再試或升級會員。",
                    retryable=True,
                )
            self.store.append(conversation_id, "user", request.message)
            if self.settings.mode == "openai":
                response = await self._openai_chat(request, conversation_id, request_id, trace_sink, user_context, plan, used_today)
            else:
                response = self._mock_chat(request, conversation_id, request_id, trace_sink, user_context, plan, used_today)
            self.store.append(conversation_id, "assistant", response.answer or "")
            return response
        except GuardrailError as exc:
            blocked_step = TraceStep(stage="guardrail", label="Guardrail 擋下問題", detail=exc.message, status="blocked")
            self._emit_trace(trace_sink, blocked_step)
            debug_enabled = request.mode == "debug" or request.response_options.include_trace is True or request.response_options.include_sql is True
            return ChatResponse(
                conversation_id=conversation_id,
                debug=DebugPayload(trace=[blocked_step]) if debug_enabled else None,
                metadata={"mode": self.settings.mode, "request_id": request_id} if debug_enabled else {},
                error=ErrorPayload(
                    code=exc.code,
                    message=exc.message,
                    retryable=exc.retryable,
                    request_id=request_id,
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive API boundary
            return ChatResponse(
                conversation_id=conversation_id,
                error=ErrorPayload(
                    code="INTERNAL_ERROR",
                    message="服務目前無法完成分析，請稍後再試。",
                    retryable=True,
                    request_id=request_id,
                ),
                warnings=[f"internal_error_type={type(exc).__name__}"],
            )

    async def chat_stream(
        self,
        request: ChatRequest,
        request_id: str,
        user: UserContext | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        """Stream audit events first, then one normalized response."""
        queue: asyncio.Queue[TraceStep] = asyncio.Queue()

        def sink(step: TraceStep) -> None:
            queue.put_nowait(step)

        task = asyncio.create_task(
            self.chat(request.model_copy(update={"stream": False}), request_id, trace_sink=sink, user=user)
        )
        yield {"event": "message_start", "data": {"conversation_id": request.conversation_id}}
        while not task.done() or not queue.empty():
            try:
                step = await asyncio.wait_for(queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            yield {"event": "trace", "data": step.model_dump()}
        response = await task
        yield {"event": "result", "data": response.model_dump(exclude_none=True)}
        yield {"event": "done", "data": {"conversation_id": response.conversation_id}}

    def _mock_chat(
        self,
        request: ChatRequest,
        conversation_id: str,
        request_id: str,
        trace_sink: TraceSink | None = None,
        user: UserContext | None = None,
        plan: PlanPolicy | None = None,
        used_today: int = 0,
    ) -> ChatResponse:
        user = user or UserContext(user_id="guest:anonymous", plan_id="guest", authenticated=False)
        plan = plan or get_plan_policy(user.plan_id)
        intent = classify(request.message)
        sql = build_sql(intent, request.message)
        result = self.database.query(
            sql,
            max_rows=plan.max_rows,
            allowed_tables=None if plan.allow_cross_table else frozenset({"auction_lots"}),
        )
        table = self._table(result, "table_1", intent.title)
        charts: list[ChartSpec] = []
        policy = choose_presentation(request, plan)
        if policy.include_chart and intent.chart_type and result.rows:
            charts.append(
                ChartSpec(
                    id="chart_1",
                    type=intent.chart_type,  # type: ignore[arg-type]
                    title=intent.title,
                    data_table_id=table.id,
                    encoding={
                        "x": intent.chart_x,
                        "y": intent.chart_y,
                        "y_format": "0.00%" if intent.chart_y == "sale_rate" else "number",
                    },
                    data=result.rows,
                )
            )
        return self._response(
            self._summarize(intent, result),
            conversation_id,
            request,
            request_id,
            result,
            [table],
            charts,
            intent,
            trace_sink=trace_sink,
            user=user,
            plan=plan,
            used_today=used_today,
        )

    async def _openai_chat(
        self,
        request: ChatRequest,
        conversation_id: str,
        request_id: str,
        trace_sink: TraceSink | None = None,
        user: UserContext | None = None,
        plan: PlanPolicy | None = None,
        used_today: int = 0,
    ) -> ChatResponse:
        user = user or UserContext(user_id="guest:anonymous", plan_id="guest", authenticated=False)
        plan = plan or get_plan_policy(user.plan_id)
        self._prepare_local_optional_packages()
        try:
            from agents import Agent, Runner, function_tool
        except ImportError as exc:
            raise GuardrailError("MODEL_NOT_INSTALLED", "尚未安裝 openai-agents；目前可先使用 Mock 模式。") from exc
        if not os.getenv("OPENAI_API_KEY", "").strip():
            raise GuardrailError(
                "MODEL_NOT_CONFIGURED",
                "尚未設定 OPENAI_API_KEY；目前請使用 Mock 模式，或只在後端環境設定 API Key。",
                retryable=False,
            )

        executed_queries: list[QueryResult] = []
        selected_skills = choose_skills(request.message)
        policy = choose_presentation(request, plan)
        trace: list[TraceStep] = []

        def record(step: TraceStep) -> None:
            trace.append(step)
            self._emit_trace(trace_sink, step)

        record(
            TraceStep(
                stage="scope",
                label="確認問題範圍",
                detail="問題已通過收藏品／藝術品拍賣資料範圍檢查。",
            )
        )
        record(
            TraceStep(
                stage="context",
                label="讀取對話上下文",
                detail=f"已載入 {max(0, len(self.store.history(conversation_id, limit=plan.history_messages)) - 1)} 則前文，供 Agent 理解追問。",
            )
        )
        record(
            TraceStep(
                stage="skills",
                label="啟用分析 Skills",
                detail="、".join(skill.name for skill in selected_skills),
            )
        )
        record(
            TraceStep(
                stage="catalog",
                label="準備資料字典",
                detail=f"Agent 可自行選擇 {len(self.catalog.tables)} 張資料表，不使用固定問題範本。",
            )
        )
        record(
            TraceStep(
                stage="agent",
                label="Agent 規劃分析方式",
                detail="由模型依問題自行判斷需要的表格、欄位、篩選條件與計算方式。",
            )
        )

        @function_tool
        def get_dataset_catalog() -> str:
            """Return approved columns, allowed values, null rules and relationships before writing SQL."""
            record(
                TraceStep(
                    stage="catalog",
                    label="Agent 讀取資料字典",
                    detail="已提供五張資料表與欄位給 Agent 自行選擇。",
                )
            )
            payload = self.catalog.agent_payload()
            return json.dumps(payload, ensure_ascii=False)

        @function_tool
        def execute_readonly_sql(sql: str) -> str:
            """Execute one validated read-only SQL query over the auction dataset."""
            record(TraceStep(stage="sql", label="Agent 產生 SQL", detail=sql.strip()))
            try:
                result = self.database.query(
                    sql,
                    max_rows=plan.max_rows,
                    allowed_tables=None if plan.allow_cross_table else frozenset({"auction_lots"}),
                )
            except GuardrailError as exc:
                record(
                    TraceStep(
                        stage="guardrail",
                        label="SQL 被 Guardrail 擋下",
                        detail=exc.message,
                        status="blocked",
                    )
                )
                raise
            executed_queries.append(result)
            record(
                TraceStep(
                    stage="query",
                    label="SQL 通過唯讀驗證並完成查詢",
                    detail=f"回傳 {len(result.rows)} 筆資料。",
                )
            )
            return json.dumps(
                {"columns": result.columns, "rows": result.rows[:100], "truncated": result.truncated},
                ensure_ascii=False,
                default=str,
            )

        agent = Agent(
            name="AI 藝術品拍賣資料查詢 Agent",
            model=self.settings.openai_model,
            instructions=(
                "你是藝術品拍賣資料研究助手。只能回答藝術品拍賣資料問題。"
                "不要套用固定問題範本；先使用 get_dataset_catalog 了解欄位，再自行選擇資料表並使用 execute_readonly_sql。"
                "不得捏造欄位或數字。"
                "SQL 的文字條件必須原樣使用資料字典的 allowed_values，不得自行翻成英文；例如 sale_status 只能是『成交』『流拍』『撤拍』。"
                "成交率預設定義為 sale_status='成交' 的件數除以全部拍品數，除非使用者另有指定。"
                + ("使用者若要求拍品圖片，SQL 必須一併選取 image_url、lot_id、title_zh 與 auction_date，讓前端能顯示圖片。" if policy.include_images else "")
                + "只能產生單一唯讀 SELECT/WITH 查詢，結果要說明樣本數、分母與模擬資料限制。"
                + f"目前方案為{plan.label}；單次查詢最多回傳 {plan.max_rows} 筆。"
                + ("可使用五張資料表做跨表分析。" if plan.allow_cross_table else "只能查詢 auction_lots，不可做跨資料表分析。")
                + "工具回傳的 JSON 只供你讀取，絕對不要直接貼回 JSON、函式結果或欄位包裝。請用繁體中文回答，文字簡短具體；若前端已有表格或圖片，文字只說明結論，不要重複完整表格。不要輸出隱藏思考，只需說明結論與可審計的資料依據。\n"
                + f"可用分析工作流：\n{skill_instructions(request.message)}"
            ),
            tools=[get_dataset_catalog, execute_readonly_sql],
        )
        history = self.store.history(conversation_id, limit=plan.history_messages)
        if history and history[-1].get("role") == "user" and history[-1].get("content") == request.message:
            history = history[:-1]
        input_items = history + [{"role": "user", "content": request.message}]
        result = await Runner.run(agent, input_items)
        record(
            TraceStep(
                stage="answer",
                label="Agent 整理答案",
                detail="已將查詢結果整理成文字、表格與可選圖表。",
            )
        )

        tables = [
            self._table(query_result, f"table_{index}", "查詢結果")
            for index, query_result in enumerate(executed_queries, 1)
        ]
        charts = self._charts_for_openai(executed_queries, tables, request, enabled=policy.include_chart)
        images: list[ImageSpec] = []
        if policy.include_images:
            for query_result in executed_queries:
                images.extend(self._images(query_result, request))
            images = images[: policy.max_images]
        sql = "\n\n".join(query.sql for query in executed_queries)
        answer = self._clean_answer(
            str(result.final_output),
            remove_tables=policy.include_table,
            remove_image_urls=policy.include_images,
        )
        debug_enabled = request.mode == "debug" or request.response_options.include_trace is True or request.response_options.include_sql is True
        debug = (
            DebugPayload(
                skills=[{"id": skill.id, "name": skill.name, "purpose": skill.purpose} for skill in selected_skills],
                trace=trace,
                sql=[query.sql for query in executed_queries],
            )
            if debug_enabled
            else None
        )
        return ChatResponse(
            answer=answer,
            conversation_id=conversation_id,
            blocks=build_blocks(tables, charts, images, policy),
            debug=debug,
            tables=tables,
            charts=charts,
            images=images,
            trace=trace,
            sql=sql,
            sources=[SourceSpec(type="dataset", table="auction_lots", description="DuckDB 示範拍賣資料")],
            warnings=[],
            disclosure=DISCLOSURE,
            metadata={
                "mode": "openai",
                "model": self.settings.openai_model,
                "request_id": request_id,
                "executed_query_count": len(executed_queries),
                "plan": plan.plan_id,
                "plan_label": plan.label,
                "usage_used_today": used_today,
                "usage_remaining_today": (
                    max(0, plan.daily_questions - used_today)
                    if plan.daily_questions is not None
                    else None
                ),
                "presentation": {
                    "table": policy.include_table,
                    "chart": policy.include_chart,
                    "images": policy.include_images,
                },
            },
        )

    def _prepare_local_optional_packages(self) -> None:
        """Make the project-local optional SDK usable without changing global Python."""
        package_dir = self.settings.project_root / ".tools" / "python-packages"
        if not package_dir.exists():
            return
        site.addsitedir(str(package_dir))
        for extra in (package_dir / "win32", package_dir / "win32" / "lib"):
            if extra.exists():
                site.addsitedir(str(extra))
        system32 = package_dir / "pywin32_system32"
        if system32.exists():
            os.environ["PATH"] = f"{system32}{os.pathsep}{os.environ.get('PATH', '')}"

    def _response(
        self,
        answer: str,
        conversation_id: str,
        request: ChatRequest,
        request_id: str,
        result: QueryResult,
        tables: list[TableResult],
        charts: list[ChartSpec],
        intent: QueryIntent,
        trace_sink: TraceSink | None = None,
        user: UserContext | None = None,
        plan: PlanPolicy | None = None,
        used_today: int = 0,
    ) -> ChatResponse:
        user = user or UserContext(user_id="guest:anonymous", plan_id="guest", authenticated=False)
        plan = plan or get_plan_policy(user.plan_id)
        policy = choose_presentation(request, plan)
        representative_lots = self._representative_lots(result) if intent.key == "lot_detail" else []
        images = (self._images(result, request) if intent.key == "lot_detail" else [])[:policy.max_images]
        charts = charts if policy.include_chart else []
        warnings: list[str] = []
        if result.truncated:
            warnings.append("結果已達到回傳筆數上限。")
        trace = [
            TraceStep(stage="scope", label="確認問題範圍", detail="問題已通過收藏品／藝術品拍賣資料範圍檢查。"),
            TraceStep(stage="skills", label="啟用分析 Skills", detail="、".join(skill.name for skill in choose_skills(request.message))),
            TraceStep(stage="sql", label="產生唯讀查詢", detail=result.sql),
            TraceStep(stage="query", label="查詢完成", detail=f"回傳 {len(result.rows)} 筆資料。"),
            TraceStep(stage="answer", label="整理答案", detail="已依回傳策略整理必要內容。"),
        ]
        for step in trace:
            self._emit_trace(trace_sink, step)
        debug_enabled = request.mode == "debug" or request.response_options.include_trace is True or request.response_options.include_sql is True
        return ChatResponse(
            answer=self._clean_answer(answer, remove_tables=policy.include_table, remove_image_urls=policy.include_images),
            conversation_id=conversation_id,
            blocks=build_blocks(tables, charts, images, policy),
            debug=(
                DebugPayload(
                    skills=[{"id": skill.id, "name": skill.name, "purpose": skill.purpose} for skill in choose_skills(request.message)],
                    trace=trace,
                    sql=[result.sql],
                )
                if debug_enabled
                else None
            ),
            tables=tables,
            charts=charts if request.response_options.include_charts else [],
            representative_lots=representative_lots,
            images=images,
            sql=result.sql,
            sources=[SourceSpec(type="dataset", table="auction_lots", description="2020–2025 模擬拍賣資料")],
            warnings=warnings,
            disclosure=DISCLOSURE,
            metadata={
                "mode": "mock",
                "model": "deterministic-mock",
                "sample_size": len(result.rows),
                "request_id": request_id,
                "query_truncated": result.truncated,
                "intent": intent.key,
                "plan": plan.plan_id,
                "plan_label": plan.label,
                "usage_used_today": used_today,
                "usage_remaining_today": (
                    max(0, plan.daily_questions - used_today)
                    if plan.daily_questions is not None
                    else None
                ),
                "presentation": {
                    "table": policy.include_table,
                    "chart": policy.include_chart,
                    "images": policy.include_images,
                },
            },
        )

    @staticmethod
    def _summarize(intent: QueryIntent, result: QueryResult) -> str:
        rows = result.rows
        if not rows:
            return "目前查不到符合條件的資料。"
        if intent.key in {"sale_rate", "annual_sale_rate", "house_ranking", "artist_ranking"}:
            top = max(rows, key=lambda row: float(row.get("sale_rate") or 0))
            label = top.get("category") or top.get("auction_house") or top.get("artist_name") or top.get("year")
            return f"目前資料中，{label}的成交率最高，為 {top.get('sale_rate')}%。樣本數為 {top.get('sample_size', '各列不同')}。"
        if intent.key in {"sales", "annual_sales"}:
            total = sum(float(row.get("total_sold_price") or 0) for row in rows)
            top = max(rows, key=lambda row: float(row.get("total_sold_price") or 0))
            label = top.get("category") or top.get("year")
            return f"只計入成交品後，合計成交總額約 RMB {total:,.0f}；其中 {label}最高，約 RMB {float(top.get('total_sold_price') or 0):,.0f}。"
        if intent.key == "status":
            summary = "、".join(f"{row['sale_status']} {row['percentage']}%" for row in rows)
            return f"成交狀態分布為：{summary}。"
        if intent.key == "counts":
            total = sum(int(row.get("row_count") or 0) for row in rows)
            return f"目前符合條件的拍品共有 {total:,} 筆。"
        if intent.key == "estimate":
            top = rows[0]
            return f"成交平均價最高的是「{top.get('category')}」，約 RMB {float(top.get('average_sold_price') or 0):,.0f}。"
        if intent.key == "lot_detail":
            return f"以下提供 {len(rows)} 筆代表性拍品明細；若要看圖片，請在回傳選項開啟 include_images。"
        total = sum(int(row.get("row_count") or 0) for row in rows)
        return f"目前資料庫包含 {len(rows)} 個資料表，列數合計 {total:,}。"

    @staticmethod
    def _table(result: QueryResult, table_id: str, title: str) -> TableResult:
        columns = [
            ColumnSpec(key=column, label=column, type=_infer_type(result.rows, column))
            for column in result.columns
        ]
        return TableResult(id=table_id, title=title, columns=columns, rows=result.rows, row_count=len(result.rows))

    @staticmethod
    def _representative_lots(result: QueryResult) -> list[RepresentativeLot]:
        lots: list[RepresentativeLot] = []
        for row in result.rows:
            if not row.get("lot_id") or not row.get("title_zh") or not row.get("category"):
                continue
            lots.append(
                RepresentativeLot(
                    lot_id=str(row["lot_id"]),
                    title_zh=str(row["title_zh"]),
                    category=str(row["category"]),
                    auction_date=str(row.get("auction_date") or ""),
                    image_url=str(row["image_url"]) if row.get("image_url") else None,
                )
            )
        return lots

    @staticmethod
    def _images(result: QueryResult, request: ChatRequest) -> list[ImageSpec]:
        if request.response_options.include_images is False:
            return []
        images: list[ImageSpec] = []
        for row in result.rows:
            url = row.get("image_url")
            if not url:
                continue
            images.append(
                ImageSpec(
                    url=str(url),
                    source="故宮 Open Data 圖片欄位",
                    source_url="https://digitalarchive.npm.gov.tw/opendata/",
                    caption=f"{row.get('title_zh', '拍品')}（{row.get('lot_id', '')}）",
                    disclosure="圖片來自故宮開放資料；拍賣公司、價格與成交狀態為本專案模擬欄位。",
                )
            )
        return images

    @staticmethod
    def _charts_for_openai(
        results: list[QueryResult],
        tables: list[TableResult],
        request: ChatRequest,
        enabled: bool | None = None,
    ) -> list[ChartSpec]:
        if enabled is None:
            enabled = request.response_options.include_charts is True
        if not enabled or not results:
            return []
        result = results[0]
        columns = set(result.columns)
        year_column = _first_column(columns, ("year", "年度", "年份", "auction_year"), contains=("year", "年度", "年份"))
        category_column = _first_column(columns, ("category", "類別", "分類"))
        rate_column = _first_column(columns, ("sale_rate", "成交率", "成交比例"), contains=("rate", "成交率"))
        total_column = _first_column(columns, ("total_sold_price", "成交總額", "總成交額"), contains=("sold_price", "成交額"))
        if year_column and rate_column:
            return [ChartSpec(id="chart_1", type="line", title="年度成交率", data_table_id=tables[0].id, encoding={"x": year_column, "y": rate_column, "y_format": "0.00%"}, data=result.rows)]
        if category_column and rate_column:
            return [ChartSpec(id="chart_1", type="bar", title="成交率比較", data_table_id=tables[0].id, encoding={"x": category_column, "y": rate_column, "y_format": "0.00%"}, data=result.rows)]
        if category_column and total_column:
            return [ChartSpec(id="chart_1", type="bar", title="成交總額比較", data_table_id=tables[0].id, encoding={"x": category_column, "y": total_column, "y_format": "RMB"}, data=result.rows)]
        return []

    @staticmethod
    def _clean_answer(answer: str, *, remove_tables: bool, remove_image_urls: bool) -> str:
        """Keep the text channel concise; structured blocks carry the data."""
        text = answer.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict) and isinstance(parsed.get("answer"), str):
                    text = parsed["answer"].strip()
            except json.JSONDecodeError:
                pass
        lines = text.splitlines()
        if remove_tables:
            lines = [line for line in lines if not line.strip().startswith("|")]
            paragraphs = "\n".join(lines).split("\n\n")
            if paragraphs:
                # Structured table blocks carry the rows; retain only the short lead sentence.
                lines = [line for line in paragraphs[0].splitlines() if line.strip()]
                lines = lines[:1]
        text = "\n".join(lines)
        if remove_image_urls:
            text = re.sub(r"https?://\S+", "", text)
            text = re.sub(r"圖片\s*[:：]\s*", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text or "查詢結果如下。"

    @staticmethod
    def _emit_trace(trace_sink: TraceSink | None, step: TraceStep) -> None:
        if trace_sink is not None:
            trace_sink(step)


def _infer_type(rows: list[dict], column: str) -> str:
    for row in rows:
        value = row.get(column)
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (int, float)):
            return "number"
        if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value):
            return "date"
        if value is not None:
            return "string"
    return "string"


def _first_column(columns: set[str], exact: tuple[str, ...], contains: tuple[str, ...] = ()) -> str | None:
    for candidate in exact:
        if candidate in columns:
            return candidate
    for column in columns:
        if any(token.lower() in column.lower() for token in contains):
            return column
    return None
