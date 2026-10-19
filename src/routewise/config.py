"""Runtime settings, read from environment variables (and a local .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Tier:
    name: str
    model: str
    effort: str | None = None  # output_config.effort; None = model default


@dataclass(frozen=True)
class Settings:
    cheap: Tier
    strong: Tier
    default_tier: str
    daily_budget_usd: float
    db_path: str
    max_tokens_default: int

    def tier(self, name: str) -> Tier:
        return self.cheap if name == "cheap" else self.strong


def load_settings() -> Settings:
    load_dotenv()
    env = os.environ.get
    return Settings(
        cheap=Tier(
            "cheap",
            env("ROUTEWISE_CHEAP_MODEL", "claude-haiku-5-5"),
            env("ROUTEWISE_CHEAP_EFFORT", "low") or None,
        ),
        strong=Tier(
            "strong",
            env("ROUTEWISE_STRONG_MODEL", "claude-sonnet-5-5"),
            env("ROUTEWISE_STRONG_EFFORT", "medium") or None,
        ),
        default_tier=env("ROUTEWISE_DEFAULT_TIER", "strong"),
        daily_budget_usd=float(env("ROUTEWISE_DAILY_BUDGET_USD", "2.00")),
        db_path=env("ROUTEWISE_DB_PATH", "routewise.sqlite"),
        max_tokens_default=int(env("ROUTEWISE_MAX_TOKENS_DEFAULT", "4096")),
    )
