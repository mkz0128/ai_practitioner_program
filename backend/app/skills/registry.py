from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SkillDefinition:
    """A small, provider-neutral description of one analysis workflow."""

    id: str
    name: str
    purpose: str
    triggers: tuple[str, ...]
    outputs: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


# These definitions are the local equivalents of the six Workspace skill zips.
# They deliberately describe workflow and safety, rather than depending on a
# specific model provider or connector.
SKILL_REGISTRY: tuple[SkillDefinition, ...] = (
    SkillDefinition(
        id="analysis-intake",
        name="分析問題接收",
        purpose="把自然語言問題整理成指標、維度、篩選條件與時間範圍。",
        triggers=("比較", "分析", "哪個", "最高", "最低", "趨勢", "排名"),
        outputs=("question_scope", "metric", "dimensions", "filters"),
    ),
    SkillDefinition(
        id="dataset-scan",
        name="資料集檢查",
        purpose="確認表格、欄位、筆數、來源與模擬資料揭露。",
        triggers=("資料集", "資料庫", "欄位", "schema", "幾筆", "筆數"),
        outputs=("catalog", "row_count", "provenance", "warnings"),
    ),
    SkillDefinition(
        id="query-crafting",
        name="查詢規劃",
        purpose="產生單一唯讀、受限筆數的 DuckDB SQL。",
        triggers=("sql", "查詢", "成交率", "成交額", "成交價", "估價", "排名"),
        outputs=("sql", "bounded_query", "table_result"),
    ),
    SkillDefinition(
        id="analysis-qa",
        name="分析檢閱",
        purpose="檢查分母、狀態、樣本數、NULL 與模擬資料揭露。",
        triggers=("驗證", "可信", "比例", "樣本", "結果", "為什麼"),
        outputs=("quality_notes", "sample_size", "disclosure"),
    ),
    SkillDefinition(
        id="visual-storytelling",
        name="視覺敘事",
        purpose="依結果欄位選擇適合的長條圖、折線圖或表格。",
        triggers=("圖表", "圖", "趨勢", "比較", "排名"),
        outputs=("chart_spec", "encoding"),
    ),
    SkillDefinition(
        id="dashboard-prototype",
        name="儀表板回傳",
        purpose="把答案、SQL、表格、圖表、圖片與來源組成前端可直接使用的 JSON。",
        triggers=("展示", "儀表板", "看", "列出", "明細", "圖片"),
        outputs=("answer", "tables", "charts", "images", "sources"),
    ),
)


def choose_skills(message: str) -> list[SkillDefinition]:
    """Select workflows deterministically; the model is not required for routing."""
    lowered = message.lower()
    selected: list[SkillDefinition] = []
    for skill in SKILL_REGISTRY:
        if any(trigger.lower() in lowered for trigger in skill.triggers):
            selected.append(skill)
    # Every valid collection question still needs intake, query, QA and packaging.
    required = {"analysis-intake", "query-crafting", "analysis-qa", "dashboard-prototype"}
    for skill in SKILL_REGISTRY:
        if skill.id in required and skill not in selected:
            selected.append(skill)
    return selected


def skill_instructions(message: str) -> str:
    selected = choose_skills(message)
    return "\n".join(f"- {skill.name}：{skill.purpose}" for skill in selected)
