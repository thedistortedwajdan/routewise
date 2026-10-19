"""Unit tests with a fake provider client. Real-provider checks live in scripts/ and the
replay harness; these tests only guard the gateway's own logic."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from routewise.app import create_app
from routewise.config import Settings, Tier
from routewise.gateway import Gateway
from routewise.ledger import Ledger
from routewise.pricing import cost_usd
from routewise.translate import UnsupportedRequest, to_anthropic


class FakeClient:
    def __init__(self):
        self.calls = []
        self.messages = self

    async def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="hi")],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=200),
            stop_reason="end_turn",
        )


def make(tmp_path, budget=2.0, default="strong"):
    s = Settings(
        cheap=Tier("cheap", "claude-haiku-5-5", "low"),
        strong=Tier("strong", "claude-sonnet-5-5", "medium"),
        default_tier=default,
        daily_budget_usd=budget,
        db_path=str(tmp_path / "t.sqlite"),
        max_tokens_default=512,
    )
    client = FakeClient()
    gw = Gateway(s, Ledger(s.db_path), client)
    return TestClient(create_app(gw)), client, gw


BODY = {"model": "auto", "messages": [{"role": "user", "content": "hello"}]}


def test_cost_math():
    assert cost_usd("claude-sonnet-5-5", 1_000_000, 1_000_000) == pytest.approx(12.0)
    assert cost_usd("claude-haiku-5-5", 100_000, 0) == pytest.approx(0.01)
    # Haiku long-prompt pricing kicks in above 100K input tokens.
    assert cost_usd("claude-haiku-5-5", 200_000, 0) == pytest.approx(0.10)


def test_translate_system_and_stop():
    out = to_anthropic(
        {
            "messages": [
                {"role": "system", "content": "be brief"},
                {"role": "user", "content": [{"type": "text", "text": "x"}]},
            ],
            "stop": "END",
            "temperature": 0.2,
        },
        512,
    )
    assert out["system"] == "be brief"
    assert out["stop_sequences"] == ["END"]
    assert out["max_tokens"] == 512
    assert "temperature" not in out


def test_translate_rejects_unsupported():
    with pytest.raises(UnsupportedRequest):
        to_anthropic({"stream": True, "messages": []}, 1)
    with pytest.raises(UnsupportedRequest):
        to_anthropic({"messages": [{"role": "assistant", "content": "x"}]}, 1)


def test_roundtrip_and_ledger(tmp_path):
    tc, client, _ = make(tmp_path)
    r = tc.post("/v1/chat/completions", json=BODY)
    assert r.status_code == 200
    j = r.json()
    assert j["choices"][0]["message"]["content"] == "hi"
    assert j["routewise"]["tier"] == "strong"
    assert client.calls[0]["model"] == "claude-sonnet-5-5"
    assert client.calls[0]["output_config"] == {"effort": "medium"}
    s = tc.get("/v1/stats").json()
    assert s["tiers"]["strong"]["requests"] == 1
    assert s["total_cost_usd"] == pytest.approx(cost_usd("claude-sonnet-5-5", 1000, 200))


def test_force_cheap_via_alias(tmp_path):
    tc, client, _ = make(tmp_path)
    r = tc.post("/v1/chat/completions", json={**BODY, "model": "cheap"})
    assert r.json()["routewise"]["route_reason"] == "forced:alias"
    assert client.calls[0]["model"] == "claude-haiku-5-5"


def test_budget_guard_blocks_before_calling_provider(tmp_path):
    tc, client, _ = make(tmp_path, budget=0.0001)
    assert tc.post("/v1/chat/completions", json=BODY).status_code == 200
    r = tc.post("/v1/chat/completions", json=BODY)
    assert r.status_code == 429
    assert r.json()["error"]["type"] == "budget_exceeded"
    assert len(client.calls) == 1


def test_bad_requests_return_400(tmp_path):
    tc, _, _ = make(tmp_path)
    assert tc.post("/v1/chat/completions", json={**BODY, "stream": True}).status_code == 400
    assert tc.post("/v1/chat/completions", content="not json").status_code == 400
