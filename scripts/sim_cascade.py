"""Offline cascade simulation from recorded per-item results of two tiers.

Rule: use the cheap answer unless the cheap model's confidence is in ESCALATE; else use the
strong answer. Cost = cheap cost for every item + strong cost for escalated items (real
recorded per-item costs). This is a simulation over recorded outputs, not a live run.

Usage: python scripts/sim_cascade.py runs/sklearn_localize/results.jsonl
"""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    rows = [json.loads(line) for line in fh]
cheap = {r["number"]: r for r in rows if r["tier"] == "cheap"}
strong = {r["number"]: r for r in rows if r["tier"] == "strong"}
nums = sorted(cheap.keys() & strong.keys())
n = len(nums)
all_strong_cost = sum(strong[k]["cost_usd"] for k in nums)
all_cheap_cost = sum(cheap[k]["cost_usd"] for k in nums)


def acc(pick):
    return sum((pick(k))["module_hit"] for k in nums) / n


print(f"n={n}")
print(f"all cheap : acc={acc(lambda k: cheap[k]):.3f} cost=${all_cheap_cost:.4f}")
print(f"all strong: acc={acc(lambda k: strong[k]):.3f} cost=${all_strong_cost:.4f}")
for name, esc in [("escalate low", {"low", ""}), ("escalate low+medium", {"low", "medium", ""})]:
    escalated = [k for k in nums if cheap[k].get("confidence", "") in esc]
    pick = lambda k, esc=esc: strong[k] if cheap[k].get("confidence", "") in esc else cheap[k]
    cost = all_cheap_cost + sum(strong[k]["cost_usd"] for k in escalated)
    print(f"cascade ({name}): escalated {len(escalated)}/{n} acc={acc(pick):.3f} cost=${cost:.4f} "
          f"= {100*cost/all_strong_cost:.1f}% of all-strong")
