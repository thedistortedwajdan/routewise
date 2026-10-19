"""Run labelled GitHub issues through routewise tiers and score against maintainer labels.

Task: classify an issue as bug / documentation / feature. Ground truth is the label the
project's maintainers actually applied (issues with exactly one of the three labels).

Usage:
  python scripts/eval_classify.py --data data/sklearn_issues.jsonl --tiers cheap,strong
Results go to runs/<name>/results.jsonl; the ledger is runs/<name>/ledger.sqlite.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

import anthropic

from routewise.config import load_settings
from routewise.gateway import Gateway
from routewise.ledger import Ledger

LABEL_MAP = {"Bug": "bug", "Documentation": "documentation", "New Feature": "feature"}
SYSTEM = (
    "You triage GitHub issues for the scikit-learn project. Classify the issue into exactly "
    "one category: bug (something behaves incorrectly or crashes), documentation (docs are "
    "wrong, missing or unclear), or feature (a request for new functionality or behaviour). "
    "Answer with a single lowercase word: bug, documentation, or feature."
)


def load_examples(path: str) -> list[dict]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        hit = [LABEL_MAP[x] for x in r["labels"] if x in LABEL_MAP]
        if len(hit) == 1:
            out.append({**r, "truth": hit[0]})
    return out


def parse(text: str) -> str:
    t = text.strip().lower()
    for lab in ("documentation", "feature", "bug"):
        if lab in t:
            return lab
    return "unparsed"


async def run_tier(gw: Gateway, tier: str, examples: list[dict], conc: int) -> list[dict]:
    sem = asyncio.Semaphore(conc)

    async def one(ex: dict) -> dict:
        body = {
            "model": tier,
            "max_tokens": 400,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Title: {ex['title']}\n\n{ex['body']}"},
            ],
        }
        async with sem:
            try:
                r = await gw.complete(body)
            except Exception as e:  # noqa: BLE001  keep going; record the failure
                return {"number": ex["number"], "tier": tier, "truth": ex["truth"],
                        "pred": "error", "error": f"{type(e).__name__}: {e}"}
        return {
            "number": ex["number"], "tier": tier, "truth": ex["truth"],
            "pred": parse(r["choices"][0]["message"]["content"]),
            "cost_usd": r["routewise"]["cost_usd"],
            "in_tok": r["usage"]["prompt_tokens"], "out_tok": r["usage"]["completion_tokens"],
        }

    return await asyncio.gather(*(one(e) for e in examples))


def report(results: list[dict]) -> None:
    by_tier: dict[str, list[dict]] = {}
    for r in results:
        by_tier.setdefault(r["tier"], []).append(r)
    for tier, rs in by_tier.items():
        ok = sum(r["pred"] == r["truth"] for r in rs)
        cost = sum(r.get("cost_usd", 0) for r in rs)
        errs = sum(r["pred"] in ("error", "unparsed") for r in rs)
        print(f"{tier:7s} n={len(rs)} accuracy={ok/len(rs):.3f} cost=${cost:.4f} "
              f"errors/unparsed={errs}")
        conf = Counter((r["truth"], r["pred"]) for r in rs)
        for (t, p), n in sorted(conf.items()):
            print(f"    truth={t:13s} pred={p:13s} {n}")
    if {"cheap", "strong"} <= by_tier.keys():
        c = {r["number"]: r for r in by_tier["cheap"]}
        s = {r["number"]: r for r in by_tier["strong"]}
        both = [n for n in c if n in s]
        cc = sum(c[n]["pred"] == c[n]["truth"] for n in both)
        ss = sum(s[n]["pred"] == s[n]["truth"] for n in both)
        only_s = sum(s[n]["pred"] == s[n]["truth"] and c[n]["pred"] != c[n]["truth"]
                     for n in both)
        only_c = sum(c[n]["pred"] == c[n]["truth"] and s[n]["pred"] != s[n]["truth"]
                     for n in both)
        agree = sum(c[n]["pred"] == s[n]["pred"] for n in both)
        print(f"paired n={len(both)}: cheap {cc}, strong {ss}; strong-only-right {only_s}, "
              f"cheap-only-right {only_c}; tiers agree on {agree}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--tiers", default="cheap,strong")
    ap.add_argument("--name", default="classify")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=8)
    a = ap.parse_args()

    examples = load_examples(a.data)
    if a.limit:
        examples = examples[: a.limit]
    print(f"{len(examples)} labelled examples: {Counter(e['truth'] for e in examples)}")

    run_dir = Path("runs") / a.name
    run_dir.mkdir(parents=True, exist_ok=True)
    settings = load_settings()
    gw = Gateway(settings, Ledger(str(run_dir / "ledger.sqlite")), anthropic.AsyncAnthropic())

    results: list[dict] = []
    for tier in a.tiers.split(","):
        results += await run_tier(gw, tier, examples, a.concurrency)
    with (run_dir / "results.jsonl").open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    report(results)
    print("ledger summary:", json.dumps(gw.ledger.summary()["tiers"]))


if __name__ == "__main__":
    asyncio.run(main())
