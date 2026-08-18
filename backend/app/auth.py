from __future__ import annotations

import hmac
import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UserContext:
    """Minimal demo identity. Replace token lookup with real auth later."""

    user_id: str
    plan_id: str
    authenticated: bool


def resolve_user(authorization: str | None, anonymous_id: str | None) -> UserContext:
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    member_token = os.getenv("DEMO_MEMBER_TOKEN", "").strip()
    if token and member_token and hmac.compare_digest(token, member_token):
        return UserContext(user_id="demo_member", plan_id="member", authenticated=True)

    safe_anonymous_id = re.sub(r"[^A-Za-z0-9_.:-]", "", (anonymous_id or "anonymous"))[:80] or "anonymous"
    # Unknown tokens never grant privileges; they fall back to the guest plan.
    return UserContext(user_id=f"guest:{safe_anonymous_id}", plan_id="guest", authenticated=False)
