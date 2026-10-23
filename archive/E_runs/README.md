# E臂_受限Agent评测 —— 结果区（2026-08-27 建立）

> E 臂（方案 v2.15/v2.16 §3.E 两段式受限 Agent）评测产物归档区。
> 程序：`py\E_Agent\run_agent_eval.py`；系统本体 `py\E_Agent\agent_core.py`。

## 目录约定（每个评测集一个 run 目录，不可覆盖）

```
E臂_受限Agent评测/
├─ agent_challenge__<UTC时间戳>/   挑战集 45 题 ×3（探索性功能测试）
│   ├─ sample_results.jsonl        逐次完整记录（意图/路由/工具块/誊写/忠实性/延迟）
│   ├─ run_manifest.json           依赖哈希（DuckDB/溶解度表/registry）+ LLM 身份
│   └─ metrics_summary.md          （分析脚本生成）
├─ agent_642__<UTC时间戳>/         642 主集 ×3（回顾性；检索与誊写忠实度口径）
├─ agent_external__<UTC时间戳>/    外部集 64 题 ×3（前瞻口径；7 DB/41 ML/16 拒绝）
└─ agent_smoke__<UTC时间戳>/       冒烟测试（3 题）
```

## 运行方式（本机 LM Link 已确认可用）

```
cd C:\Users\AS\Desktop\CET
set PYTHONUTF8=1
C:\Users\AS\AppData\Local\Programs\Python\Python314\python.exe py\E_Agent\run_agent_eval.py --set smoke
... --set challenge --repeats 3
... --set 642      --repeats 3
... --set external --repeats 3
```

锚点模型：`cet-gguf/qwen3-4b-instruct-2507@q4_k_m`（与 A/C 臂 Base 同部署身份，默认 Reasoning=Off）。

## 口径红线

- 642 = 回顾性探索（DuckDB 命中≈100%，结果表述为**检索与誊写忠实度**，不作模型外推精度）；
- 外部集 = 前瞻外部评估（路由与安全指标主战场）；
- 挑战集 = 探索性功能测试（澄清/拒绝/饱和行为）；
- 指标：路由准确率 / 参数与单位解析准确率 / 载荷忠实率 / 拒绝 P-R + 延迟与失败率（方案 §4）。
