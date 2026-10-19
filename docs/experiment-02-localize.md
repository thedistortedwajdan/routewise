# Experiment 02: bug localisation, cheap vs strong tier

**Question:** on a harder task, does the strong tier pull ahead, and can the cheap model's own
confidence tell us when to escalate?

**Task:** given a scikit-learn issue, name the module (e.g. `linear_model`) and the source file
the fix touches. **Ground truth:** source files changed by the merged PR that closed the issue
(fetched with `scripts/fetch_fixes.py`, GitHub GraphQL `closedByPullRequestsReferences`). No LLM
judge. 110 issues from 2025-10 to 2026-10. A prediction is a "module hit" if the module is among
those the PR changed; a "file hit" if the exact file path is.

## Result

| Tier | Module acc. | File acc. | Cost (110 issues) |
|---|---|---|---|
| cheap (Haiku 5.5) | 99/110 = 90.0% | 82.7% | $0.0280 |
| strong (Sonnet 5.5) | 103/110 = 93.6% | 86.4% | $0.5157 |

Paired: strong-only-right 4, cheap-only-right 0, both right 99, both wrong 7.
Cost ratio: strong is ~18x the cheap tier.

**Cheap-model confidence is informative** (self-reported `high|medium|low`):

| Cheap confidence | n | Module acc. |
|---|---|---|
| high | 75 | 96.0% |
| medium | 24 | 91.7% |
| low | 11 | 45.5% |

## Offline cascade simulation (`scripts/sim_cascade.py`)

Use the cheap answer unless it reports low (or low/medium) confidence, then use the strong
answer. Computed from the recorded per-item outputs and per-item costs (not a live run).

| Policy | Module acc. | Cost | vs all-strong |
|---|---|---|---|
| all cheap | 90.0% | $0.028 | 5% |
| cascade (escalate low, 11 items) | 90.9% | $0.163 | 32% |
| cascade (escalate low+medium, 35 items) | 91.8% | $0.258 | 50% |
| all strong | 93.6% | $0.516 | 100% |

## What this does and does not show

- The strong tier is better by 4 items out of 110 (0/4 paired split). A sign test on that gives
  p of about 0.125, so **the accuracy gap is not statistically established at this sample size.**
- The cheap tier is already close to the strong tier on this task, so there is little for a
  router to win here. The cascade recovers 1 to 2 items for 6x to 9x the cheap-only cost.
- Escalated items are expensive: low-confidence issues are long, and long inputs dominate cost.
  Escalating 10% of items cost about 27% of the all-strong bill.
- Confidence calibration is the useful finding: "low" really does mean unreliable (45%), so it
  is a usable escalation signal, but only 11 items were low, so the estimate is rough.
- Models may have seen scikit-learn history in pre-training, which can inflate both tiers.
  Many issues also quote the traceback that names the file.

## Implication for the project

The routing idea only pays where the cheap tier fails. Two classification-style tasks both came
out near parity, so the next experiment should target tasks with a real quality gap (longer
reasoning, multi-file context) before investing in a learned router.
