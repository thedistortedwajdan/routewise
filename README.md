# routewise

A cost-routing gateway for LLM applications. It sits between your app and your model providers, sends easy requests to cheap models and hard ones to strong models, caches repeats, and measures how much money you saved against how much quality you lost.

> Status: v0 proxy works end to end against the real Anthropic API (routing is manual for now).

## Quick start

```bash
python -m venv .venv && source .venv/Scripts/activate
pip install -e ".[dev]"
cp .env.example .env          # add ANTHROPIC_API_KEY
python -m routewise --port 8000
```

```bash
curl localhost:8000/v1/chat/completions -H 'content-type: application/json'   -d '{"model":"cheap","messages":[{"role":"user","content":"Hello"}]}'
curl localhost:8000/v1/stats
```

`model` can be `cheap`, `strong`, or anything else (the default tier is used). Every request is logged to SQLite with tokens, cost, latency and the route taken. A daily budget cap (`ROUTEWISE_DAILY_BUDGET_USD`, default $2) rejects requests with HTTP 429 once reached.

Not supported yet: streaming, tool calling, images. Sampling params (`temperature`, `top_p`) are ignored because current Claude models reject non-default values.


## Why

Using the strongest model for every request is a spending decision, not an engineering one. routewise makes that trade-off explicit and measurable:

- **Route** each request to the cheapest model that can handle it.
- **Cache** repeated requests so they cost nothing.
- **Measure** cost saved vs. quality retained by replaying a request log against an "always use the best model" baseline.

## Planned architecture

```
client app ──▶ routewise gateway ──▶ difficulty router ──▶ cheap model
                    │                       └────────────▶ strong model
                    ├──▶ cache
                    └──▶ cost / quality tracking ──▶ report
```

## Roadmap

- [x] OpenAI-compatible proxy endpoint (non-streaming)
- [x] Cost ledger + daily budget guard
- [ ] Provider adapters (pluggable)
- [ ] Exact + semantic cache
- [ ] Difficulty router (rules first, learned classifier later)
- [ ] Replay harness: cost and quality vs. best-model baseline
- [ ] Dashboard / report
- [ ] CI with regression checks on routing quality

## Development

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; use .venv\Scripts\Activate.ps1 in PowerShell
pip install -e ".[dev]"
pytest
```

## License

MIT
