# API LLM direct-answer benchmark

This report is generated from immutable raw-response hashes and evaluator-side gold joins.
The bundled question set is an exploratory pilot because the historical holdout was already opened.

| Model key | Analysis set | N prompts | Numeric coverage | Micro Accuracy@10% | Macro-system Accuracy@10% | MAE (valid) | MdAPE (valid) |
|---|---|---:|---:|---:|---:|---:|---:|
| qwen3_4b_instruct_2507_base_q4km | primary_all_eligible_unique_conditions | 642 | 99.9% | 5.4% | 5.2% | 6.6820 | 321.2077% |
| qwen3_4b_instruct_2507_base_q4km | sensitivity_balanced_60_per_system | 240 | 99.9% | 5.4% | 5.4% | 7.2667 | 557.7737% |
| gemma2_9b_it_base_q4km | primary_all_eligible_unique_conditions | 642 | 100.0% | 17.0% | 15.6% | 1.2502 | 29.7669% |
| gemma2_9b_it_base_q4km | sensitivity_balanced_60_per_system | 240 | 100.0% | 15.0% | 15.0% | 1.6452 | 31.5615% |
| llama3_1_8b_instruct_base_q4km | primary_all_eligible_unique_conditions | 642 | 100.0% | 12.5% | 14.0% | 0.7469 | 29.4290% |
| llama3_1_8b_instruct_base_q4km | sensitivity_balanced_60_per_system | 240 | 100.0% | 13.8% | 13.7% | 0.6033 | 29.6668% |
| qwen3_6_27b_base_q4km | primary_all_eligible_unique_conditions | 642 | 100.0% | 23.5% | 24.0% | 1.1437 | 19.8608% |
| qwen3_6_27b_base_q4km | sensitivity_balanced_60_per_system | 240 | 100.0% | 26.2% | 26.2% | 1.0151 | 18.7492% |
| qwen3_8b_instruct_base_q4km | primary_all_eligible_unique_conditions | 642 | 100.0% | 14.8% | 11.6% | 0.6633 | 32.9953% |
| qwen3_8b_instruct_base_q4km | sensitivity_balanced_60_per_system | 240 | 100.0% | 12.1% | 12.1% | 0.6019 | 39.5700% |

Accuracy denominators include every scheduled sample. Valid-only error metrics must always be presented with numeric coverage.
Confidence intervals fix solution systems and resample origin lineages as clusters; repeated API calls remain nested within each base prompt.
The balanced 240-question sensitivity view reuses the exact responses from the 642-question primary run and adds zero API calls.
