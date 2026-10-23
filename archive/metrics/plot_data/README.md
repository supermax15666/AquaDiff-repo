# 03_最小绘图表 —— 逐图最小绘图数据（Origin 直接导入即用）

> 生成：2026-08-20（文件已按当前图号改名，2026-10-14），脚本 `10_共享_脚本/汇总与绘图/prep_plot_tables.ps1`（历史生成器）（源数据取自 02_绘图数据，可重复生成）。
> 用法：打开 Origin → 文件 > 导入 > 单个 ASCII → 选本目录对应 CSV → 按表内列直接画图。每个文件只保留该图需要的列，已按绘图要求预处理（如百分比已×100、APE 已按模型排序、布尔已转 0/1）。
> 行数说明：模型级/汇总表只有几行；散点、分布、稳定性图必须逐题（数百至数千行）；延迟箱线必须逐次调用（近万行）。行数不是冗余，是该图所需粒度。

> 旧名到新名的完整对照见 `文件对照_旧名到当前图号.md`。

## 文件 → 当前图号对照

| 文件 | 对应图 | 列与画法 |
|---|---|---|
| `表1_数据集统计.csv` | 表 1（原图 1A/图 2 漏斗） | system, n_records, n_lineages, n_unique_conditions(TBD=待重算), n_main_questions, n_sensitivity_questions；漏斗用 total 行 785→696→642 |
| `图2_温度浓度覆盖.csv` | 图 2（原图 4） | system, temperature_K, concentration_mol_L, lineage；2×2 分面散点，颜色=lineage |
| `图5a_闭卷CI_B臂.csv` | 图 5（B 臂，原图 5A） | model, view(primary=主集/sensitivity=240子集), acc10_macro_percent, ci_low_percent, ci_high_percent；横向点图，实心=primary、空心=sensitivity，误差棒用 CI 两列，X 轴 0–80 |
| `图5b_闭卷CI_A臂.csv` | 图 5（A 臂，原图 5B） | 同上（A 臂五模型） |
| `图6_热图_B臂.csv` / `图6_热图_A臂.csv` | 图 6（不变） | model, system, acc10_mean_percent；热图，色阶 0–80 |
| `图7_观测预测散点_B臂.csv` | 图 7（原图 7，API 六模型） | model, system, observed, predicted_median；分模型面板散点 + y=x、±10% 线 |
| `图8_观测预测散点_A臂.csv` | **图 8**（原图 7 拆出，本地 Base 五模型） | 同上 |
| `图9a_APE累积_B臂.csv` / `图9a_APE累积_A臂.csv` | 图 9(a)（原图 8A） | model, ape_median_percent（已按模型内排序）；累计比例对 APE 画线，5%/10% 参考线 |
| `图9b_带符号误差_B臂.csv` / `图9b_带符号误差_A臂.csv` | 图 9(b)（原图 8B） | model, system, signed_error；小提琴/箱线 + 零线，按体系分面 |
| `图10a_唯一预测值数.csv` | 图 10(a)（原图 9） | model, unique_predictions（各模型唯一预测值数） |
| `图10_错误示例.csv`、`图10b_失败案例三例.csv` | 图 10（原图 9 示例） | type(tail_error/parse_or_format_failure), model, question_id, system, T, c, observed, predicted_median, ape_percent |
| `图11_Base到SFT配对.csv` | 图 11（原图 10） | Base→SFT 配对掌握度 |
| `图12a_选模面板.csv` | 图 12(a)（原图 11B） | 面板数据（24 行：体系×算法宏谱系 MdAPE 与折间范围；**折间 min/max 非统计 CI**） |
| `图12b_专用vs合并_宽表.csv` / `图12b_专用vs合并_长表.csv` | 图 12(b)（原图 11C） | 专用 vs pooled（宽表 4 行；长表 8 行供组内连线） |
| `图12_冻结汇总_权威数字.csv` | 图 12 与表 4、表 5（原图 11） | 冻结汇总权威数字（48 行，全指标） |
| `图13_统一性能对比.csv` | 图 13（不变） | 组, 条目, 642_macro%, 外部_macro% |
| `图15b_成本延迟.csv` | 图 15(b) | 各路径成本与时延 |
| `图S1_重复稳定性_B臂.csv` / `_A臂.csv` | Fig. S1 | model, system, predicted_range；按模型箱线 |
| `图S2a_运行质量_B臂.csv` / `_A臂.csv` | Fig. S2(a) | model, request_success_percent, schema_valid_percent, valid_numeric_percent, latency_median_s；点图 |
| `图S2b_时延_B臂.csv` / `_A臂.csv` | Fig. S2(b) | model, latency_seconds；对数 X 轴箱线（图注注明基础设施依赖） |
| `表S27_思考敏感性指标.csv` | 表 S27（原讨论 4.2） | view(sensitivity=开思考), acc10_percent, ci_low/high, acc5_percent, mae, mdape_percent, r2；**关思考侧 26.2% 取自 `图5b_闭卷CI_A臂.csv` 中 qwen3.6-27b 的 sensitivity 视图** |
| `源数据_图5_B臂模型指标.csv` / `源数据_图5_A臂模型指标.csv` | **源数据**（服务图 5、表 3） | 模型级指标原始表 |
| `源数据_题目级_A臂.csv` / `源数据_题目级_B臂.csv` | **源数据**（服务图 6/7/8/9、Fig. S1） | 逐题级记录 |
| `源数据_逐次调用_A臂.csv` / `源数据_逐次调用_B臂.csv` | **源数据**（服务 Fig. S2） | 逐次调用级记录（近万行） |
| `表S27_思考敏感性_源数据.csv` | **源数据**（服务表 S27） | 240 题逐题记录 |
| `_冗余副本/` | — | 与已保留文件**字节完全相同**的重复件（原 `图11_D臂_*` 四个） |

## 尚无数据的图（待实验）

图 10（SFT 配对）、图 12（Agent 架构，方法图可先画线框）、图 13、图 14、图 15B 成本部分：数据待 C/E 臂；图 15A 红黄绿矩阵为定性图，无需数据文件。

## 纪律

- 本目录文件可随意改（工作副本）；01 目录为权威副本勿动。
- 数字与正文核对以 01 目录为准；绘图以本目录为准。
- D 臂折间范围为波动展示，正式 CI 待谱系聚类 bootstrap 实现后替换。
