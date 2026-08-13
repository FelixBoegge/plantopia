"""Renders what one diagnosis cost, in tokens and money."""

import streamlit as st


def render_cost_badge(token_usage: dict[str, int] | None, cost_usd: float | None) -> None:
    """Render a one-line usage caption, or nothing at all.

    Renders nothing when no usage was recorded — every diagnosis written before
    Phase 3 has NULL columns, and a "0 tokens" badge would misreport those as free
    rather than as unmeasured. Cost is omitted on the same principle when the
    provider reported none (spec §5).
    """
    if not token_usage:
        return

    prompt = token_usage.get("prompt_tokens", 0)
    completion = token_usage.get("completion_tokens", 0)
    parts = [f"{prompt:,} in / {completion:,} out tokens"]
    if cost_usd is not None:
        parts.append(f"${cost_usd:.4f}")
    st.caption(" · ".join(parts))
