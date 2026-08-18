from __future__ import annotations

from dataclasses import dataclass

from .plans import PlanPolicy
from .schemas import ChatRequest, ChartSpec, ContentBlock, ImageSpec, TableResult


@dataclass(frozen=True)
class PresentationPolicy:
    """Decides which stable blocks are useful; the model cannot invent renderers."""

    include_table: bool
    include_chart: bool
    include_images: bool
    max_images: int


def choose_presentation(request: ChatRequest, plan: PlanPolicy | None = None) -> PresentationPolicy:
    message = request.message.lower()
    options = request.response_options
    image_request = any(token in message for token in ("圖片", "照片", "圖像", "看圖", "附圖"))
    chart_request = any(token in message for token in ("圖表", "趨勢", "折線", "長條圖", "視覺化"))
    comparison_request = any(token in message for token in ("比較", "排名", "前三", "前 3", "最高", "最低", "最貴", "第一名", "第二名"))
    list_request = any(token in message for token in ("列出", "明細", "清單", "表格", "幾筆", "多少件"))

    include_images = options.include_images if options.include_images is not None else image_request
    include_chart = options.include_charts if options.include_charts is not None else (chart_request and not image_request)
    if plan is not None:
        include_images = include_images and plan.allow_images
        include_chart = include_chart and plan.allow_charts
    if image_request and not chart_request:
        include_chart = False

    if options.include_tables is not None:
        include_table = options.include_tables
    elif image_request and not list_request:
        # A follow-up such as「我想看第一名的照片」is an image request.  The
        # image block already carries the lot identity; do not duplicate the
        # same row as a table merely because the sentence contains「第一名」.
        include_table = False
    elif chart_request and not list_request:
        # A trend/chart request is best represented by one visual block. The
        # chart carries the values; add a table only when the user explicitly
        # asks to list rows/details or overrides include_tables.
        include_table = False
    else:
        include_table = True

    # If a guest asks for a trend, preserve useful data by falling back to a
    # bounded table when chart access is not included in that plan.
    if chart_request and not include_chart and not image_request and not list_request:
        include_table = True

    return PresentationPolicy(
        include_table=include_table,
        include_chart=include_chart,
        include_images=include_images,
        max_images=plan.max_images if plan is not None else 20,
    )


def build_blocks(
    tables: list[TableResult],
    charts: list[ChartSpec],
    images: list[ImageSpec],
    policy: PresentationPolicy,
) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []
    if policy.include_table:
        for table in tables:
            blocks.append(
                ContentBlock(
                    id=table.id,
                    type="table",
                    title=table.title,
                    data=table.model_dump(),
                )
            )
    if policy.include_chart:
        for chart in charts:
            blocks.append(
                ContentBlock(
                    id=chart.id,
                    type="chart",
                    title=chart.title,
                    data=chart.model_dump(),
                )
            )
    if policy.include_images and images:
        blocks.append(
            ContentBlock(
                id="images_1",
                type="image",
                title="拍品圖片",
                data={"items": [image.model_dump() for image in images]},
            )
        )
    return blocks
