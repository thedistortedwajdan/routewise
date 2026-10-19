"""Per-token prices (USD per million tokens) and cost computation.

Prices are first-party Anthropic API list prices as of 2026-10. Verify them against the
provider's pricing page and your invoice. Cache-token pricing is not modelled yet, so cost
is computed from input_tokens and output_tokens only.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    input_per_mtok: float
    output_per_mtok: float
    # Some models charge more once the prompt exceeds a size threshold.
    long_threshold: int | None = None
    long_input_per_mtok: float = 0.0
    long_output_per_mtok: float = 0.0


PRICES: dict[str, Price] = {
    "claude-haiku-5-5": Price(0.10, 0.50, 100_000, 0.50, 2.50),
    "claude-sonnet-5-5": Price(2.00, 10.00),
    "claude-opus-5-5": Price(4.00, 20.00),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price = PRICES.get(model)
    if price is None:
        raise KeyError(f"no price configured for model {model!r}")
    in_rate, out_rate = price.input_per_mtok, price.output_per_mtok
    if price.long_threshold is not None and input_tokens > price.long_threshold:
        in_rate, out_rate = price.long_input_per_mtok, price.long_output_per_mtok
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000
