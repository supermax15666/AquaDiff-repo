# 3.D_ML：四体系冻结数值后端（研究方案 v2.6 第 3.D 节，条款自 v2.2 未变）

本目录实现 research_plan_simple.md（v2.2）第 **3.D 节"冻结的数值后端"**：
对 NaCl–H₂O、KCl–H₂O、LiCl–H₂O、CaCl₂–H₂O 四个溶液体系，
各自比较六种候选数值模型，按**谱系宏平均 MdAPE** 选出每体系的专用模型，
注册冻结后供实验臂 E（本地 Agent + MCP + DuckDB）调用；同时训练 pooled
对照模型，用于回答论文比较之一——**"分体系建模是否必要"**。

## 1. 目录结构

```text
py/3.D_ML/
├── code/                          # 程序与配置
│   ├── config.json                # 协议配置（数据源、CV、选模指标、适用域）
│   ├── requirements.txt           # 依赖（scikit-learn、joblib、openpyxl、numpy）
│   ├── ml_common.py               # 哈希/原子写/JSON 工具
│   ├── data_builder.py            # 四工作簿 → 冻结训练数据集（复用题库构建逻辑）
│   ├── models.py                  # 六个冻结候选模型定义
│   ├── evaluate.py                # 谱系分组 5 折 CV、指标、选模、pooled 对照
│   ├── run_backend.py             # CLI：build / evaluate / register / status
│   └── README.md                  # 本文件
└── output/                        # 全部产物（不提交代码仓库的键钥类内容除外）
    ├── 冻结汇总.csv                   # register 生成：48 行指标权威汇总（CSV 为准，UTF-8 BOM）
    ├── 冻结汇总.xlsx                  # register 生成：人类可读 Excel（7 个工作表，阅读用）
    ├── dataset/
    │   ├── ml_conditions.jsonl        # 冻结训练数据集（642 条合格唯一条件）
    │   └── dataset_manifest.json      # 数据溯源、过滤日志、哈希、谱系计数
    ├── evaluation/<协议指纹>/
    │   ├── results.json               # 完整 CV 结果（专/池两套、折级明细、选模）
    │   ├── manuscript_metrics.csv     # 论文表格级指标 CSV
    │   └── report.md                  # 摘要报告（入选模型 + pooled 对照）
    └── registry/<协议指纹>/
        ├── registry.json              # 注册清单（模型、CV 指标、适用域、产物哈希）
        ├── <体系>.joblib              # 该体系注册的专用模型（全量数据重训）
        └── <体系>.pooled_control.joblib  # pooled 对照产物（只用于比较，不作 Agent 后端）
```

## 2. 环境安装

```powershell
cd E:\Desktop\CET_docment\CET_docment\py\3.D_ML\code
python -m pip install -r requirements.txt
```

## 3. 数据构建（build）

```powershell
python run_backend.py --config config.json build
```

数据来源与过滤规则与题库构建完全一致（复用
`py/LLM_API_direct/prepare_questions.py` 的读表、同条件合并与过滤逻辑）：

- 数据源：`分谱系数据/` 下四个工作簿的 `Confirmed_Records` 工作表；
- 同一 (system, T, c) 的多条文献记录合并为中位数共识值；
- 排除：c=0 的无限稀释/派生记录、多谱系冲突条件、派生谱系（DERIVED: / HARNED_1955:D0）；
- 训练目标：`diffusion_1e9_m2_s`（单位固定 `10^-9 m^2/s`），特征：`temperature_K`、`concentration_mol_L`；
- **强一致性校验**：合格条件集合必须与冻结的 642 题 evaluator gold
  （`py/LLM_API_direct/questions/four_system_all_gold.evaluator.jsonl`）
  的 condition_id **精确相等**，任何偏差直接报错，防止与 A/B/C 臂数据口径漂移。

构建结果：NaCl 174、KCl 247、LiCl 132、CaCl₂ 89，共 642 条；数据集与
manifest 均记录 SHA-256。所有产物写 `output/dataset/`。

## 4. 六个候选模型（models.py，超参冻结）

| 模型键 | 说明 |
|---|---|
| `polynomial_ridge` | 二次多项式特征 (T, c, T², Tc, c²) + Ridge(alpha=1.0) |
| `rbf_svr` | 特征标准化 + SVR(RBF, C=1.0, epsilon=0.1) |
| `random_forest` | 300 棵树、min_samples_leaf=2、固定 random_state、n_jobs=1（避免受限环境下多线程命名管道失败；结果与并行度无关） |
| `gradient_boosting` | 300 轮、learning_rate=0.05、max_depth=3、固定 random_state |
| `gaussian_process` | Constant·RBF + White 噪声核、normalize_y、0 次重启优化（确定性） |
| `dummy_median` | 训练目标中位数基线（最低参考） |

超参数为**预冻结**的固定值（不做网格搜索/调参），避免按测试结果调参。
所有随机种子固定（`random_state=20260814`），整个评估可逐位复现。
模型代码的 SHA-256 参与协议指纹。

## 5. 交叉验证方案（evaluate）

- `GroupKFold(n_splits=5)`，**按 `origin_lineage_id` 整谱系分组**——同一文献谱系
  的所有记录要么全在训练、要么全在测试，防止近重复条件在训练/测试间泄漏；
- 不 shuffle，折划分完全确定；
- 对每个体系 × 每个模型做 5 折 CV，聚合全部测试预测后计算指标；
- **pooled 对照**：同一个折划分下，用其他体系的训练折 + 本体系训练折一起
  训练"全体系版"模型（system 作 one-hot 特征），在本体系测试折上预测——
  与专用模型**同题配对**，差值可直接解读为"分体系建模带来的收益/损失"。

## 6. 指标定义

闭卷数值口径与 A/B 臂一致：

- **主选模指标：谱系宏平均 MdAPE**（每个谱系内取 APE 中位数，再跨谱系等权
  平均）——对谱系样本量不敏感，是方案第 3.D 节指定指标；
- 同时报告：MAE、RMSE、bias、MdAPE（全部预测）、Accuracy@5%、Accuracy@10%、
  P95 APE、max APE、覆盖率（本地模型恒为 100%，字段保留用于跨臂同口径）；
- 空答/拒答/越界在本阶段不存在（注册后由适用域检查在调用时兜底）。

## 7. 选模与注册（register）

```powershell
python run_backend.py --config config.json register
```

- 按 `selection.primary_metric`（宏谱系 MdAPE，越小越好）对每体系六模型排序，
  tie-break 用 MAE；
- 选中的模型在**该体系全部 642 条中的对应子集**上重训（CV 用于选模，全量重训
  用于交付），保存为 `<体系>.joblib`；
- 适用域：矩形盒（temperature_K 与 concentration_mol_L 的 [min, max]）。
  **盒外输入必须结构化拒绝**（rejection_policy=structured_refusal），
  不得用其他体系模型代替——这是方案第 3.D 节的硬规则，臂 E 的宿主程序必须
  在调用前校验；
- pooled 对照同样全量重训并留档（`<体系>.pooled_control.joblib`），仅用于
  "专用 vs pooled"比较，**不作为 Agent 后端**；
- 注册产物全部记录 SHA-256，写入 `registry.json`；
- register 结束后自动在 `output/` 生成《冻结汇总.csv》（权威，UTF-8 BOM，CSV 为准）与
  《冻结汇总.xlsx》（7 个工作表：说明/入选模型/专用模型对比/pooled对照/专用vs pooled/
  全部明细/折级明细）；Excel 仅作阅读，逐位权威数据仍以 evaluation/registry 指纹目录为准。

## 8. 协议指纹与冻结

- 评价目录与注册目录均以**协议指纹**（config 内容 + 数据集 SHA-256 +
  models/evaluate/data_builder 代码 SHA-256 的稳定哈希）命名；
- `config.protocol_frozen` 为 `false` 时，评价/注册产物会被标记为未冻结；
  论文主表使用前必须：核对结果 → 把 `protocol_frozen` 置 `true` → **完整重跑**
  evaluate 与 register（不允许只改标记不重跑）；
- 更换模型、特征、超参、划分或数据过滤规则后，协议指纹变化，旧产物保留，
  新产物落在新目录，不覆盖。

## 9. 与实验臂 E（Agent）的对接约定

- Agent 路由顺序（方案第 3.E 节）：DuckDB 命中 → 返回实验值；未命中但在
  适用域内 → 调用本目录注册的**该体系专用模型**；域外 → 结构化拒绝；
- 宿主程序负责：解析体系/单位、校验适用域（读 registry.json 的
  applicability_domain）、调用 joblib 产物、检查输出正数与单位一致性；
- 语言模型只做理解与路由，最终数值必须来自 DuckDB 或本目录注册产物。

## 10. 常用命令

```powershell
python run_backend.py --config config.json build      # 构建/校验冻结数据集
python run_backend.py --config config.json evaluate   # 六模型 5 折 CV + pooled 对照
python run_backend.py --config config.json register   # 选模、全量重训、注册与适用域
python run_backend.py --config config.json status     # 查看数据集/评价/注册状态
```

## 11. 复现步骤（正式使用顺序）

1. `pip install -r requirements.txt`；
2. `build` 并核对 manifest 中过滤日志与 642 题 gold 一致性；
3. `evaluate`，检查 `report.md` 与 `results.json`（含折级明细）；
4. 确认结果后：`config.json` 中 `protocol_frozen` 置 `true`，重新执行
   `evaluate` 与 `register`（新指纹目录）——本目录已于 2026-08-15 按此完成冻结（见 §13）；
5. 冻结后的 registry 目录即臂 E 的数值后端来源。

## 12. 论文表述边界（与方案第 9 节一致）

- 四体系数据来自已打开的回顾性数据池：本目录一切结果都是**回顾性、探索性**
  数值模型比较，不能写成 blind、prospective、independent external 或
  confirmatory；
- 专用模型优于 pooled 或优于语言模型的结论，只能限定在"当前四体系 + 现有
  谱系"范围内；
- LiCl 与 CaCl₂ 谱系较少，逐体系推断仅作描述性；
- 数值后端不声称"提高底层回归算法精度"；Agent 若引用本目录产物，其收益
  属于工具路由增强，不是 ML 模型本身的创新点。

## 13. 当前结果快照

- 历史探索性首跑（协议指纹 `38b8bc02…488a16`，protocol_frozen=false）保留未动，仅作对照；
- **冻结重跑（协议指纹 `ffbc8b45…63ad6`，protocol_frozen=true，2026-08-15）为论文主表依据**：
  在冻结配置下完整重跑 build/evaluate/register。选模与全部指标与首轮一致，仅 Random Forest
  的指标存在 ≤2 ULP 的末位浮点差异（`n_jobs` 由 -1 改为 1 所致；RF 未在任何体系入选，
  对选模、注册与论文数字无影响）。

| 体系 | 入选模型 | 宏谱系 MdAPE% | MAE (1e-9 m²/s) | CV Acc@10% |
|---|---:|---:|---:|
| NaCl-H₂O | Gaussian Process | 2.13 | 0.1008 | 86.8% |
| KCl-H₂O | Polynomial Ridge | 2.70 | 0.0797 | 99.6% |
| LiCl-H₂O | Gradient Boosting | 4.68 | 0.3622 | 35.6% |
| CaCl₂-H₂O | Gradient Boosting | 4.52 | 0.0555 | 83.1% |

pooled 对照在同一折划分上：NaCl 2.55%、KCl 4.04%、LiCl 2.60%、CaCl₂ 3.55%（宏谱系 MdAPE）。
NaCl/KCl/CaCl₂ 专用模型更好，LiCl 上 pooled 数据借用占优。

register 自动生成 `output/冻结汇总.csv`（权威，CSV 为准）与 `output/冻结汇总.xlsx`（阅读用）。
论文引用冻结目录 `evaluation/ffbc8b45…63ad6` 与 `registry/ffbc8b45…63ad6`，
主表数字取自冻结汇总.csv。
