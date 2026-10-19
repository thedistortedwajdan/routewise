"""Bug-localisation eval: given an issue, name the scikit-learn module and file that the fix
touches. Ground truth = source files changed by the merged PR that closed the issue.

Usage:
  python scripts/eval_localize.py --issues data/sklearn_issues.jsonl \
      --fixes data/sklearn_fixes.jsonl --tiers cheap,strong --name sklearn_localize
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path

import anthropic

from routewise.config import load_settings
from routewise.gateway import Gateway
from routewise.ledger import Ledger

SRC_SUFFIXES = (".py", ".pyx", ".pxd", ".tp", ".pxd.tp", ".pyx.tp")
IGNORED_FILES = {"sklearn/_min_dependencies.py"}
MODULES = (
    "base calibration callback cluster compose covariance cross_decomposition datasets "
    "decomposition discriminant_analysis dummy ensemble exceptions experimental "
    "feature_extraction feature_selection frozen gaussian_process impute inspection isotonic "
    "kernel_approximation kernel_ridge linear_model manifold metrics mixture model_selection "
    "multiclass multioutput naive_bayes neighbors neural_network pipeline preprocessing "
    "random_projection semi_supervised svm tree utils _loss _build_utils externals top_level"
)
SYSTEM = (
    "You are helping triage issues for the scikit-learn library. Given a GitHub issue, decide "
    "where in the scikit-learn source code the fix would most likely be made.\n"
    f"Choose the module from this list: {MODULES}. Use 'top_level' for files directly in "
    "sklearn/ such as sklearn/base.py or sklearn/pipeline.py.\n"
    "Reply with exactly three lines and nothing else:\n"
    "module: <module name from the list>\n"
    "file: <your best guess of the single source file path, e.g. sklearn/linear_model/_ridge.py>\n"
    "confidence: <low|medium|high>"
)


def module_of(path: str) -> str:
    parts = path.split("/")
    return parts[1] if len(parts) > 2 else "top_level"


def source_files(files: list[str]) -> list[str]:
    return [
        f for f in files
        if f.startswith("sklearn/") and "/tests/" not in f and f.endswith(SRC_SUFFIXES)
        and f not in IGNORED_FILES
    ]


def load_examples(issues: str, fixes: str) -> list[dict]:
    by_num = {}
    for line in Path(issues).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        by_num[r["number"]] = r
    out = []
    for line in Path(fixes).read_text(encoding="utf-8").splitlines():
        fx = json.loads(line)
        src = source_files(fx["files"])
        if src and fx["number"] in by_num:
            out.append({
                **by_num[fx["number"]],
                "truth_files": src,
                "truth_modules": sorted({module_of(f) for f in src}),
            })
    return out


def parse(text: str) -> dict:
    def grab(key: str) -> str:
        m = re.search(rf"^\s*{key}\s*:\s*(\S+)", text, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip("`'\".,").lower() if m else ""
    return {"module": grab("module"), "file": grab("file"), "confidence": grab("confidence")}


async def run_tier(gw: Gateway, tier: str, examples: list[dict], conc: int) -> list[dict]:
    sem = asyncio.Semaphore(conc)

    async def one(ex: dict) -> dict:
        body = {
            "model": tier,
            "max_tokens": 1000,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Title: {ex['title']}\n\n{ex['body']}"},
            ],
        }
        base = {"number": ex["number"], "tier": tier, "truth_modules": ex["truth_modules"],
                "truth_files": ex["truth_files"], "chars": len(ex["title"]) + len(ex["body"])}
        async with sem:
            try:
                r = await gw.complete(body)
            except Exception as e:  # noqa: BLE001  keep going; record the failure
                return {**base, "error": f"{type(e).__name__}: {e}", "module_hit": False,
                        "file_hit": False}
        p = parse(r["choices"][0]["message"]["content"])
        return {
            **base, **p,
            "module_hit": p["module"] in ex["truth_modules"],
            "file_hit": p["file"] in [f.lower() for f in ex["truth_files"]],
            "cost_usd": r["routewise"]["cost_usd"],
            "out_tok": r["usage"]["completion_tokens"],
        }

    return await asyncio.gather(*(one(e) for e in examples))


def report(results: list[dict]) -> None:
    tiers = sorted({r["tier"] for r in results})
    for t in tiers:
        rs = [r for r in results if r["tier"] == t]
        n = len(rs)
        mh = sum(r["module_hit"] for r in rs)
        fh = sum(r["file_hit"] for r in rs)
        cost = sum(r.get("cost_usd", 0) for r in rs)
        errs = sum("error" in r or not r.get("module") for r in rs)
        print(f"{t:7s} n={n} module_acc={mh/n:.3f} file_acc={fh/n:.3f} cost=${cost:.4f} "
              f"errors/unparsed={errs}")
        for conf in ("high", "medium", "low", ""):
            sub = [r for r in rs if r.get("confidence", "") == conf]
            if sub:
                print(f"    confidence={conf or 'none':6s} n={len(sub):3d} "
                      f"module_acc={sum(r['module_hit'] for r in sub)/len(sub):.3f}")
    if len(tiers) == 2:
        a = {r["number"]: r for r in results if r["tier"] == tiers[0]}
        b = {r["number"]: r for r in results if r["tier"] == tiers[1]}
        both = [k for k in a if k in b]
        print(f"paired n={len(both)}: {tiers[0]}-only-right "
              f"{sum(a[k]['module_hit'] and not b[k]['module_hit'] for k in both)}, "
              f"{tiers[1]}-only-right "
              f"{sum(b[k]['module_hit'] and not a[k]['module_hit'] for k in both)}, "
              f"both-right {sum(a[k]['module_hit'] and b[k]['module_hit'] for k in both)}, "
              f"both-wrong {sum(not a[k]['module_hit'] and not b[k]['module_hit'] for k in both)}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--issues", required=True)
    ap.add_argument("--fixes", required=True)
    ap.add_argument("--tiers", default="cheap,strong")
    ap.add_argument("--name", default="localize")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=8)
    a = ap.parse_args()

    examples = load_examples(a.issues, a.fixes)
    if a.limit:
        examples = examples[: a.limit]
    print(f"{len(examples)} examples with a merged fixing PR touching source files")

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


if __name__ == "__main__":
    asyncio.run(main())
