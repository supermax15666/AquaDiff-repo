# E 臂 Agent 评测指标 · challenge（162 样本）

- set: challenge
- n_samples: 162
- route_accuracy: 0.963
- route_confusion: {'clarify->db_hit': 6}
- intent_accuracy: 0.7593
- intent_json_parse_success: 0.9815
- faithfulness: 1.0
- faithfulness_violations: {}
- refusal_precision: 1.0
- refusal_recall: 1.0
- refusal_counts: {'true_refusal_questions': 27, 'agent_refusal_questions': 27, 'both': 27}
- acc10_any_repeat: None
- acc10_all_repeats: None
- per_system_acc10: {}
- latency_s: {'intent_mean': 0.66, 'final_mean': 0.86}
- intent_fail_examples: [('A1', 'missing_fields', 'ok', 0, 0.5, 'mol/L'), ('A1', 'missing_fields', 'ok', 0, 0.5, 'mol/L'), ('A1', 'missing_fields', 'ok', 0, 0.5, 'mol/L'), ('A2', 'missing_fields', 'ok', 298.15, 0, 'unknown'), ('A2', 'missing_fields', 'ok', 298.15, 0, 'unknown'), ('A2', 'missing_fields', 'ok', 298.15, 0, 'unknown'), ('A5', 'ambiguous', 'ok', 298.15, 0.5, 'mol/L'), ('A5', 'ambiguous', 'ok', 298.15, 0.5, 'mol/L')]