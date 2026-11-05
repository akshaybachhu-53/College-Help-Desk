# Evaluation summary

| System | Model | Runs | Accuracy | Groundedness | OOS refusal | False refusal | Routing | Agent logged refusals | Median latency (s) |
|---|---|---|---|---|---|---|---|---|---|
| multi | helpdesk-qwen3:8b | 1 | 73% (22/30) | 100% (16/16) | 86% (6/7) | 13% (3/23) | 87% (26/30) | 62% (5/8) | 52.775000000000006 |

## Accuracy by category

| System | Model | policy | schedule | email | oos |
|---|---|---|---|---|---|
| multi | helpdesk-qwen3:8b | 83% (10/12) | 62% (5/8) | 50% (2/4) | 83% (5/6) |

## Questions whose answers changed across runs

| System | Model | Question | Correct per run | Change |
|---|---|---|---|---|
