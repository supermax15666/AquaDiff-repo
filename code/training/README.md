# C 臂（SFT 微调）正式工作区 —— README

> 本目录是 C 臂（SFT 微调）的**正式**代码与冻结物工作区（方案第 3.C 节，
> v2.10 冻结、v2.11 仅调整 thinking 敏感性条款、C 臂条款不变；方案 §7 指定
> "本地 SFT 程序：py/微调"）。旧两体系 524 题流程已移至
> `py/past/微调/`，仅作历史 pilot 参考，其任何结果不得进论文主表。
> 接手前必读：根目录 `C臂SFT交接文档.md` → `research_plan_simple.md`(v2.11) →
> `AGENTS.md` → `PROGRESS.md`。

## 目录结构

```text
py/微调/
├── AGENTS.md                        本子树约束（含外部集保密纪律）
├── README.md                        本文件
├── 外部前瞻集检索与冻结方案.md       检索范围/排除基线/容差/条数目标/录入契约（§17 执行件，已冻结）
├── 提示家族冻结清单.md               A/B/C 三族文案 + 哈希（已冻结）
├── audit_freeze_external.py         外部集审计+冻结脚本（precheck / freeze 两模式）
├── freeze_prompt_families.py        提示家族冻结脚本（已执行，勿重跑）
├── frozen/
│   └── prompt_families_frozen.json  提示家族机器可读冻结记录（权威哈希源）
└── external/                        外部前瞻集工作区
    ├── candidates/                  用户检索的候选数据放这里（.xlsx/.csv，列契约见检索方案第 6 节）
    ├── questions/  gold/  manifest/  audit/  sealed/
    └──                    （--freeze 一次性生成；生成后 gold 密封，禁止查看）
```

## 当前状态（2026-08-16）

| 步骤（交接文档 §5） | 状态 |
|---|---|
| 1. 外部集检索（用户）+ 审计冻结脚本 | 🔶 脚本已完成并自测通过；**用户检索未开始**（检索范围已制定） |
| 2. 冻结提示家族 A/B/C | ✅ 已冻结（`frozen/prompt_families_frozen.json` + 清单） |
| 3. 冻结训练配置模板 | ⏳ 待做 |
| 4. 训练数据生成（642 全量 + 家族 C） | ⏳ 待做（依赖步骤 1 冻结完成后才能开训） |
| 5–8. pilot 训练 → 五模型训练 → 合并/GGUF/Q4_K_M → LM Studio | ⏳ 待做（服务器） |
| 9–11. SFT 642 评测 / 掌握度分析 / 外部集统一评估 | ⏳ 待做 |
| 12. 外部集合并分析 + SFT−Base 配对 bootstrap | ⏳ 待做（C 臂代码核心，尚未实现） |

## 关键命令

```powershell
# 外部集 precheck（检索期间自查，可反复运行）
python audit_freeze_external.py --precheck --candidates external\candidates

# 外部集正式审计+冻结（一次性；输出目录必须为空；冻结后 gold 密封）
python audit_freeze_external.py --candidates external\candidates --out-dir external
```

## 硬约束速览

1. 外部集在 **SFT 训练开始前**冻结（方案 §17）；冻结后任何人不得查看 gold、
   任何模型不得先跑、不得回改训练/提示/选模/超参。
2. 提示家族 A/B/C 已冻结；任何改动先升版方案（AGENTS.md 第 4 条）。
3. 训练数据必须从 642 全量重新生成（同一 gold/谱系映射、家族 C、单字段答案格式），
   禁用旧 `py/past/微调` 数据。
4. 五模型统一 LoRA 超参（方案第 15 条）；训练后禁止调参/重训；epoch 写死。
5. 合并权重哈希、GGUF 哈希、llama.cpp commit b10188（d0bfb198…）全程留档。
6. 每次改变后同步 `PROGRESS.md`。
