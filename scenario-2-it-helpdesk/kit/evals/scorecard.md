# Eval scorecard

Cases file: `my_cases.jsonl` · runs: **20** · passed: **20** (**100%**)

Turn latency: avg **2.43 s**, p95 **5.73 s** · reported cost: **$0.0181**

| case | category | result | why it failed |
|---|---|---|---|
| M-01 | policy_conflict | ✅ |  |
| M-02 | policy_conflict | ✅ |  |
| M-03 | policy_conflict | ✅ |  |
| M-04 | policy_conflict | ✅ |  |
| M-05 | conflict | ✅ |  |
| M-06 | rejection | ✅ |  |
| M-07 | tool_failure | ✅ |  |
| M-08 | guardrail | ✅ |  |
| M-09 | unknown | ✅ |  |
| M-10 | guardrail | ✅ |  |
| M-11 | clarification | ✅ |  |
| M-12 | conflict | ✅ |  |
| M-13 | policy_conflict | ✅ |  |
| M-14 | memory | ✅ |  |
| M-15 | memory | ✅ |  |
| M-16 | guardrail | ✅ |  |
| M-17 | happy_path | ✅ |  |
| M-18 | guardrail | ✅ |  |
| M-19 | grounding | ✅ |  |
| M-20 | guardrail | ✅ |  |

| category | passed |
|---|---|
| clarification | 1/1 |
| conflict | 2/2 |
| grounding | 1/1 |
| guardrail | 5/5 |
| happy_path | 1/1 |
| memory | 2/2 |
| policy_conflict | 5/5 |
| rejection | 1/1 |
| tool_failure | 1/1 |
| unknown | 1/1 |
