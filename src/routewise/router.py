"""Routing decisions. v0 is deliberately simple: explicit override or a default tier.

The difficulty-based router plugs in here later without touching the rest of the gateway.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Settings

TIER_ALIASES = {"cheap": "cheap", "strong": "strong"}


@dataclass(frozen=True)
class Decision:
    tier: str
    reason: str


def choose(settings: Settings, requested_model: str | None) -> Decision:
    """Pick a tier. A client may force one by naming a tier alias or a configured model id."""
    if requested_model in TIER_ALIASES:
        return Decision(TIER_ALIASES[requested_model], "forced:alias")
    if requested_model == settings.cheap.model:
        return Decision("cheap", "forced:model")
    if requested_model == settings.strong.model:
        return Decision("strong", "forced:model")
    return Decision(settings.default_tier, "default")
