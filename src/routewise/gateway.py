"""Core request handling: route, enforce budget, call the provider, record to the ledger."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from . import router, translate
from .config import Settings
from .ledger import Ledger, Record
from .pricing import cost_usd


class BudgetExceeded(RuntimeError):
    pass


def start_of_utc_day(now: float | None = None) -> float:
    dt = datetime.fromtimestamp(now if now is not None else time.time(), tz=timezone.utc)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


class Gateway:
    def __init__(self, settings: Settings, ledger: Ledger, client):
        self.settings = settings
        self.ledger = ledger
        self.client = client  # anthropic.AsyncAnthropic (or a test double)

    async def complete(self, req: dict) -> dict:
        s = self.settings
        params = translate.to_anthropic(req, s.max_tokens_default)
        decision = router.choose(s, req.get("model"))
        tier = s.tier(decision.tier)

        spent = self.ledger.spend_since(start_of_utc_day())
        if spent >= s.daily_budget_usd:
            raise BudgetExceeded(
                f"daily budget ${s.daily_budget_usd:.2f} reached (spent ${spent:.4f})"
            )

        if tier.effort:
            params["output_config"] = {"effort": tier.effort}
        t0 = time.perf_counter()
        resp = await self.client.messages.create(model=tier.model, **params)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        inp, out = resp.usage.input_tokens, resp.usage.output_tokens
        cost = cost_usd(tier.model, inp, out)
        self.ledger.add(
            Record(
                id=uuid.uuid4().hex,
                tier=tier.name,
                model=tier.model,
                route_reason=decision.reason,
                input_tokens=inp,
                output_tokens=out,
                cost_usd=cost,
                est_strong_cost_usd=cost_usd(s.strong.model, inp, out),
                latency_ms=latency_ms,
            )
        )
        return translate.to_openai(
            resp, model=tier.model, tier=tier.name, cost_usd=cost, route_reason=decision.reason
        )
