# routewise

A cost-routing gateway for LLM applications. It sits between your app and your model providers, sends easy requests to cheap models and hard ones to strong models, caches repeats, and measures how much money you saved against how much quality you lost.

> Status: early scaffold. Nothing is implemented yet.

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

- [ ] OpenAI-compatible proxy endpoint
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
