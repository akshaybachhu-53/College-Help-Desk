# Evaluation summary

| System | Model | Runs | Accuracy | Groundedness | OOS refusal | False refusal | Routing | Agent logged refusals | Median latency (s) |
|---|---|---|---|---|---|---|---|---|---|
| multi | helpdesk-llama3.1:8b | 3 | 83% (75/90) | 90% (43/48) | 100% (21/21) | 0% (0/69) | 87% (78/90) | 95% (18/19) | 5.77 |
| multi | helpdesk-qwen3:8b | 3 | 91% (82/90) | 100% (58/58) | 100% (21/21) | 6% (4/69) | 93% (84/90) | 74% (14/19) | 59.095 |
| single | helpdesk-llama3.1:8b | 3 | 79% (71/90) | 93% (38/41) | 100% (21/21) | 6% (4/69) | - | 48% (12/25) | 5.4350000000000005 |
| single | helpdesk-qwen3:8b | 3 | 87% (78/90) | 100% (54/54) | 95% (20/21) | 4% (3/69) | - | 89% (16/18) | 46.94 |

## Accuracy by category

| System | Model | policy | schedule | email | oos |
|---|---|---|---|---|---|
| multi | helpdesk-llama3.1:8b | 75% (27/36) | 88% (21/24) | 75% (9/12) | 100% (18/18) |
| multi | helpdesk-qwen3:8b | 78% (28/36) | 100% (24/24) | 100% (12/12) | 100% (18/18) |
| single | helpdesk-llama3.1:8b | 75% (27/36) | 75% (18/24) | 67% (8/12) | 100% (18/18) |
| single | helpdesk-qwen3:8b | 78% (28/36) | 88% (21/24) | 100% (12/12) | 94% (17/18) |

## Questions whose answers changed across runs

| System | Model | Question | Correct per run | Change |
|---|---|---|---|---|
| multi | helpdesk-llama3.1:8b | Q01 | 0 1 0 | correctness |
| multi | helpdesk-llama3.1:8b | Q05 | 1 0 1 | correctness |
| multi | helpdesk-llama3.1:8b | Q07 | 0 0 0 | wording/facts only |
| multi | helpdesk-llama3.1:8b | Q15 | 1 1 1 | wording/facts only |
| multi | helpdesk-llama3.1:8b | Q16 | 1 1 1 | wording/facts only |
| multi | helpdesk-llama3.1:8b | Q22 | 0 0 0 | wording/facts only |
| multi | helpdesk-qwen3:8b | Q04 | 1 1 1 | wording/facts only |
| multi | helpdesk-qwen3:8b | Q05 | 0 0 0 | wording/facts only |
| multi | helpdesk-qwen3:8b | Q07 | 0 1 0 | correctness |
| multi | helpdesk-qwen3:8b | Q08 | 1 1 1 | wording/facts only |
| multi | helpdesk-qwen3:8b | Q09 | 0 0 0 | wording/facts only |
| multi | helpdesk-qwen3:8b | Q10 | 1 1 1 | wording/facts only |
| multi | helpdesk-qwen3:8b | Q11 | 1 1 1 | wording/facts only |
| multi | helpdesk-qwen3:8b | Q12 | 1 1 1 | wording/facts only |
| multi | helpdesk-qwen3:8b | Q13 | 1 1 1 | wording/facts only |
| multi | helpdesk-qwen3:8b | Q16 | 1 1 1 | wording/facts only |
| multi | helpdesk-qwen3:8b | Q18 | 1 1 1 | wording/facts only |
| multi | helpdesk-qwen3:8b | Q22 | 1 1 1 | wording/facts only |
| multi | helpdesk-qwen3:8b | Q24 | 1 1 1 | wording/facts only |
| multi | helpdesk-qwen3:8b | Q29 | 1 1 1 | wording/facts only |
| single | helpdesk-llama3.1:8b | Q01 | 1 0 1 | correctness |
| single | helpdesk-llama3.1:8b | Q05 | 0 1 0 | correctness |
| single | helpdesk-llama3.1:8b | Q09 | 0 0 0 | wording/facts only |
| single | helpdesk-llama3.1:8b | Q10 | 1 1 1 | wording/facts only |
| single | helpdesk-llama3.1:8b | Q15 | 1 1 1 | wording/facts only |
| single | helpdesk-llama3.1:8b | Q16 | 1 1 1 | wording/facts only |
| single | helpdesk-llama3.1:8b | Q19 | 0 0 0 | wording/facts only |
| single | helpdesk-llama3.1:8b | Q23 | 0 1 1 | correctness |
| single | helpdesk-qwen3:8b | Q05 | 0 0 0 | wording/facts only |
| single | helpdesk-qwen3:8b | Q07 | 0 0 0 | wording/facts only |
| single | helpdesk-qwen3:8b | Q08 | 1 1 1 | wording/facts only |
| single | helpdesk-qwen3:8b | Q09 | 1 0 0 | correctness |
| single | helpdesk-qwen3:8b | Q10 | 1 1 1 | wording/facts only |
| single | helpdesk-qwen3:8b | Q13 | 1 1 1 | wording/facts only |
| single | helpdesk-qwen3:8b | Q16 | 1 1 1 | wording/facts only |
| single | helpdesk-qwen3:8b | Q17 | 1 1 1 | wording/facts only |
| single | helpdesk-qwen3:8b | Q19 | 0 0 0 | wording/facts only |
| single | helpdesk-qwen3:8b | Q22 | 1 1 1 | wording/facts only |
| single | helpdesk-qwen3:8b | Q23 | 1 1 1 | wording/facts only |
| single | helpdesk-qwen3:8b | Q24 | 1 1 1 | wording/facts only |
| single | helpdesk-qwen3:8b | Q28 | 1 0 1 | correctness |
| single | helpdesk-qwen3:8b | Q29 | 1 1 1 | wording/facts only |
