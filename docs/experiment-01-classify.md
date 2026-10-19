# Experiment 01: issue-type classification, cheap vs strong tier

**Question:** on a real, labelled task, how much accuracy do we give up by sending requests to
the cheap tier instead of the strong tier, and how much do we save?

**Data:** 302 real scikit-learn issues (created 2025-10-29 to 2026-10-19) carrying exactly one
of the maintainer labels `Bug` (169), `Documentation` (71), `New Feature` (62). Ground truth is
the label the maintainers applied. Fetched with `scripts/fetch_issues.py`.

**Method:** `scripts/eval_classify.py` sends each issue through the gateway to each tier with
the same prompt (title + full body, answer one word). Cheap = `claude-haiku-5-5` (effort low),
strong = `claude-sonnet-5-5` (effort medium). Costs are computed from provider-reported token
counts.

## Result (valid run)

| Tier | Accuracy | Cost (302 issues) |
|---|---|---|
| cheap (Haiku 5.5) | 286/302 = 94.7% | $0.0456 |
| strong (Sonnet 5.5) | 285/302 = 94.4% | $0.8971 |

Strong-only-right: 6. Cheap-only-right: 7. Tiers agreed on 285 of 302.
Cheap was ~20x cheaper with no measurable accuracy loss on this task.

## Caveats (read before quoting the numbers)

- One run, n=302. The 1-issue difference between tiers is noise, not a win for either tier.
- Maintainer labels are themselves imperfect; both tiers' "errors" include label noise.
- Single-label classification is an easy task. This does not show that cheap suffices for
  harder tasks (summarising threads, diagnosing bugs). Those are the next experiments.
- Costs use list prices from `pricing.py` and are not yet reconciled against the invoice.

## Invalid first run (kept for honesty)

The first run used `max_tokens=20`. Models spend output tokens on internal thinking, so for 19
cheap and 6 strong requests the budget ran out before any answer was written; those counted as
wrong (cheap 90.7%, strong 93.7%). That was a harness bug, not a model difference. Rerun with
`max_tokens=400` gave the table above.

**Lesson for the gateway:** a client-supplied small `max_tokens` can produce an empty reply when
thinking is on. The gateway should detect `stop_reason=max_tokens` with no text and either raise
the floor or flag it. Tracked as a TODO.
