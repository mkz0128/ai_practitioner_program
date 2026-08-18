from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanPolicy:
    """Server-side entitlements. The client cannot override these values."""

    plan_id: str
    label: str
    daily_questions: int | None
    max_rows: int
    allow_charts: bool
    allow_images: bool
    max_images: int
    allow_cross_table: bool
    history_messages: int


PLAN_POLICIES: dict[str, PlanPolicy] = {
    "guest": PlanPolicy(
        plan_id="guest",
        label="非會員",
        daily_questions=5,
        max_rows=10,
        allow_charts=False,
        allow_images=True,
        max_images=1,
        allow_cross_table=False,
        history_messages=4,
    ),
    "member": PlanPolicy(
        plan_id="member",
        label="會員",
        daily_questions=100,
        max_rows=100,
        allow_charts=True,
        allow_images=True,
        max_images=20,
        allow_cross_table=True,
        history_messages=20,
    ),
}


def get_plan_policy(plan_id: str) -> PlanPolicy:
    return PLAN_POLICIES.get(plan_id, PLAN_POLICIES["guest"])


def public_plan_summary(policy: PlanPolicy, used_today: int) -> dict[str, object]:
    remaining = None
    if policy.daily_questions is not None:
        remaining = max(0, policy.daily_questions - used_today)
    return {
        "id": policy.plan_id,
        "label": policy.label,
        "used_today": used_today,
        "daily_limit": policy.daily_questions,
        "remaining_today": remaining,
        "entitlements": {
            "max_rows": policy.max_rows,
            "charts": policy.allow_charts,
            "images": policy.allow_images,
            "max_images": policy.max_images,
            "cross_table": policy.allow_cross_table,
            "history_messages": policy.history_messages,
        },
    }
