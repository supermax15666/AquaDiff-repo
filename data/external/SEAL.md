# SEAL — external prospective test set is now FROZEN

冻结时间（UTC）：2026-08-23T11:24:34.333303+00:00

**自此刻起至最终评估前（research_plan_simple.md v2.14 第 17 条；v2.13 时序口径：训练后、任何评估前冻结）：**

1. 任何人（含用户与助手）不得查看 gold 文件内容；
2. 任何模型不得在外部集上运行（含 A 臂 Base 五模型）；
3. 不得根据外部集结果回改训练、提示、选模或超参；
4. 违规 → 前瞻性作废，外部集只能按回顾性报告。

## 哈希清单（核验用，无任何真值）

| 产物 | SHA-256 |
|---|---|
| questions | 624db157768072d2d453e6fb46e87a0983a974254def39b8a782daab677fe637 |
| gold | c09eb6d25c0b8086b4e0e136a7dc94aca202525b950c6ce66511935820a0bed5 |
| manifest content | 60db902d10e28176e9289ce245f28a071ca528a2761a43aa7bc6be4b3d55ee3f |
| manifest file | bbdfede2f376ad647400581a2ac616a99aca73b1bebeb5b0dd42fb1ff2005b08 |
| audit log | 234464179a3ea05a5a953984e31cba7875d46198660b7aa1fa3b96a84c654d91 |
| scope doc | c21de8ae5e209a5eb65f88deb836dc1268aad081bd71520365d2d8204342b61a |
| generator | 8ef9723ed7454d11a256b0fbfe96941961cdcc68f669c491d9589ef63ff2aa1b |

题数：64；逐体系：{"NaCl-H2O": 12, "KCl-H2O": 15, "LiCl-H2O": 27, "CaCl2-H2O": 10}
