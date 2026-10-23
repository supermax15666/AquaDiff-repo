# API LLM direct-answer benchmark

This report is generated from immutable raw-response hashes and evaluator-side gold joins.
The bundled question set is an exploratory pilot because the historical holdout was already opened.

| Model key | Analysis set | N prompts | Numeric coverage | Micro Accuracy@10% | Macro-system Accuracy@10% | MAE (valid) | MdAPE (valid) |
|---|---|---:|---:|---:|---:|---:|---:|
| deepseek-v4-pro | primary_all_eligible_unique_conditions | 642 | 99.9% | 45.5% | 51.1% | 0.3195 | 11.5880% |
| deepseek-v4-pro | sensitivity_balanced_60_per_system | 240 | 100.0% | 52.4% | 52.4% | 0.2480 | 9.2652% |
| glm-5.2 | primary_all_eligible_unique_conditions | 642 | 100.0% | 47.2% | 49.7% | 0.2628 | 10.9574% |
| glm-5.2 | sensitivity_balanced_60_per_system | 240 | 100.0% | 50.7% | 50.7% | 0.2228 | 9.5749% |
| qwen3.8-max | primary_all_eligible_unique_conditions | 642 | 100.0% | 45.3% | 44.9% | 0.3286 | 11.3801% |
| qwen3.8-max | sensitivity_balanced_60_per_system | 240 | 100.0% | 47.6% | 47.6% | 0.2721 | 10.9677% |
| doubao-seed-2-1-pro-260628 | primary_all_eligible_unique_conditions | 642 | 100.0% | 49.3% | 52.5% | 0.3330 | 10.1683% |
| doubao-seed-2-1-pro-260628 | sensitivity_balanced_60_per_system | 240 | 100.0% | 51.9% | 51.9% | 0.2596 | 9.8549% |
| MiniMax-M3 | primary_all_eligible_unique_conditions | 642 | 99.9% | 39.6% | 40.1% | 0.4539 | 14.2982% |
| MiniMax-M3 | sensitivity_balanced_60_per_system | 240 | 99.9% | 39.3% | 39.3% | 0.3596 | 13.7931% |
| kimi-k3 | primary_all_eligible_unique_conditions | 642 | 99.4% | 63.9% | 62.7% | 0.1809 | 6.6368% |
| kimi-k3 | sensitivity_balanced_60_per_system | 240 | 98.9% | 61.4% | 61.4% | 0.1692 | 7.3644% |

Accuracy denominators include every scheduled sample. Valid-only error metrics must always be presented with numeric coverage.
Confidence intervals fix solution systems and resample origin lineages as clusters; repeated API calls remain nested within each base prompt.
The balanced 240-question sensitivity view reuses the exact responses from the 642-question primary run and adds zero API calls.
