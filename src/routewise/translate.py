"""Translate between OpenAI chat-completions format and Anthropic Messages format."""

from __future__ import annotations

import time
import uuid


class UnsupportedRequest(ValueError):
    """The request uses a feature the gateway does not support (yet)."""


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
            else:
                raise UnsupportedRequest("only text content parts are supported")
        return "".join(parts)
    raise UnsupportedRequest("message content must be a string or a list of text parts")


def to_anthropic(req: dict, default_max_tokens: int) -> dict:
    if req.get("stream"):
        raise UnsupportedRequest("stream=true is not supported yet")
    if req.get("tools") or req.get("functions"):
        raise UnsupportedRequest("tool calling is not supported yet")
    if int(req.get("n", 1) or 1) != 1:
        raise UnsupportedRequest("n > 1 is not supported")

    system_parts: list[str] = []
    messages: list[dict] = []
    for m in req.get("messages", []):
        role = m.get("role")
        if role in ("system", "developer"):
            system_parts.append(_text_of(m.get("content")))
        elif role in ("user", "assistant"):
            messages.append({"role": role, "content": _text_of(m.get("content"))})
        else:
            raise UnsupportedRequest(f"role {role!r} is not supported")
    if not messages or messages[0]["role"] != "user":
        raise UnsupportedRequest("conversation must start with a user message")

    out: dict = {
        "max_tokens": req.get("max_completion_tokens")
        or req.get("max_tokens")
        or default_max_tokens,
        "messages": messages,
    }
    if system_parts:
        out["system"] = "\n\n".join(system_parts)
    stop = req.get("stop")
    if stop:
        out["stop_sequences"] = [stop] if isinstance(stop, str) else list(stop)
    # temperature/top_p are intentionally not forwarded: current Claude models reject
    # non-default sampling values.
    return out


_FINISH = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "refusal": "content_filter",
}


def to_openai(resp, *, model: str, tier: str, cost_usd: float, route_reason: str) -> dict:
    text = "".join(b.text for b in resp.content if b.type == "text")
    inp, out = resp.usage.input_tokens, resp.usage.output_tokens
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": _FINISH.get(resp.stop_reason, "stop"),
            }
        ],
        "usage": {"prompt_tokens": inp, "completion_tokens": out, "total_tokens": inp + out},
        "routewise": {"tier": tier, "route_reason": route_reason, "cost_usd": cost_usd},
    }
