# 3.D_ML 输出目录

本目录只存放 `py/3.D_ML/code` 生成的产物（研究方案 v2.2 第 3.D 节数值后端）：

- `冻结汇总.csv`：`register` 自动生成的权威汇总（48 行指标，UTF-8 BOM，CSV 为准）；
- `冻结汇总.xlsx`：`register` 自动生成的阅读用 Excel（7 个工作表），数值以同名 CSV 为准；
- `Origin导入模板/`：论文图 10 的 Origin 导入数据（面板数据 CSV、专用 vs pooled CSV）与导入说明，
  由 `code/export_origin_template.py` 从冻结结果生成；
- `dataset/`：冻结训练数据集与溯源 manifest；
- `evaluation/<协议指纹>/`：谱系分组 5 折 CV 结果、论文指标 CSV、摘要报告；
- `registry/<协议指纹>/`：每体系注册的专用模型（joblib）、pooled 对照产物与注册清单。

规则：

- 不得手工移动、覆盖或合并已完成产物；协议或配置变化后重跑会落在新指纹目录；
- 旧两体系或历史 pilot 结果不得混入本目录；
- `冻结汇总.csv/.xlsx` 随每次 `register` 重写（反映最近一次注册），逐位权威数据仍以指纹目录为准；
- 论文主表引用 `protocol_frozen=true` 的目录（当前冻结指纹：`ffbc8b45…63ad6`）。
