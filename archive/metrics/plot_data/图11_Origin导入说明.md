# Origin 新手分步教程（论文图 10：数值后端性能）

> 适用：Origin 2021 及以上（菜单为英文界面名称）。数据来源：冻结结果 `ffbc8b45…63ad6`，
> 由 `py/3.D_ML/code/export_origin_template.py` 生成，UTF-8 BOM + 逗号分隔。
> 重要口径：当前**没有统计置信区间**，误差条用"折间 min–max"（5 折波动），图注必须如实说明；
> 结果均为谱系分组 5 折 CV 内部估计，无独立外部验证。

## 文件清单

| 文件 | 行数 | 用途 |
|---|---|---|
| `图10_面板数据_专用模型.csv` | 24 | 图 10A：各体系 × 6 模型点图（已含"模型顺序、折间min/max"列） |
| `图10_专用vs_pooled_长表.csv` | 8 | 图 10B：专用 vs pooled 成对点图（推荐用这个长表） |
| `图10_专用vs_pooled.csv` | 4 | 图 10B 的宽表备份（含 Δ 与解读，画图不必用） |

---

## 第 0 步：导入 CSV（两张图共用）

1. 打开 Origin，直接把 CSV 文件**拖进** Origin 空白区（或 `File → Import → Single ASCII`）；
2. 弹出对话框（Import ASCII Options）：确认 **Delimiter = Comma**、表头行自动识别为 1，点 OK；
3. 导入后：工作表列名显示为中文（Long Name），面板数据表应有 24 行、长表 8 行。

---

## 第 1 步：图 10A —— 四体系 × 六模型点图

### 1a. 把工作表按"体系"拆成 4 个（新手最稳做法）

1. 右键面板数据工作表的**表名标签**（左下角 Sheet1 那个）→ `Split Worksheet`（拆分工作表）→ Split by Group → 选 **体系** 列 → OK；
2. 得到 4 个子表：NaCl-H2O、KCl-H2O、LiCl-H2O、CaCl2-H2O，每表 6 行。

### 1b. 每个子表画一张散点图（重复 4 次，以 NaCl 为例）

1. 在 NaCl-H2O 子表里：右键 **模型** 列头 → `Set As → Y`；右键 **宏谱系MdAPE%** 列头 → `Set As → X`；
2. 把 **模型** 列设为分类：右键列头 → `Properties` → Options 页 → 勾选 **Set as Categorical**；
3. 按住 Ctrl 点选这两列 → 菜单 `Plot → Basic 2D → Scatter`（散点）；
4. 出现图层后调 Y 轴顺序：双击 Y 轴 → Tick Labels 页，确认类型为"Text from Dataset"；
   若模型顺序不对，回到子表按 **模型顺序** 列升序排序（右键表 → Sort Worksheet → 按 模型顺序）再重画。

### 1c. 给"入选"模型标色（每张图一次）

1. 单击图中任一数据点**一次**（选中整组点）→ 再单击目标点**一次**（选中单个点）→ **双击**该点；
2. 在弹出的 Plot Details 里改 Symbol：实心圆、加深色（如深红）；其余模型保持浅色空心；
3. Dummy 基线：同上操作把该点改成**灰色**。

### 1d. 加"折间波动"误差条（可选，但论文图要）

1. 面板数据 CSV 里已有现成的 **折间min_MdAPE%** 与 **折间max_MdAPE%** 两列；
2. 在子表中：右键图 → `Plot Setup` → 下方 Plot List 选中该散点 → 在列角色区把
   **折间min_MdAPE%** 拖到 **Y Error (lower)**、**折间max_MdAPE%** 拖到 **Y Error (upper)** → OK；
3. ⚠️ 图注必须写："误差条为五个测试折间的 MdAPE 范围，非统计置信区间；正式 CI 需谱系聚类 bootstrap"。

### 1e. 合并成 2×2 面板

1. 四张图都画好后：菜单 `Graph → Merge Graph Windows`（合并图形窗口）；
2. 选择 4 张图 → 排列选 2 行 × 2 列 → 勾选 "Link Axes"（X/Y 同刻度）→ OK；
3. 统一 X 轴标题："宏谱系 MdAPE（%）"，Y 轴标题："候选模型"；X 范围建议 0–10，**不得截断坐标**
   （KCl 的 Dummy=45.5%，在图中用灰色点+文字标注数值即可，或图注说明）。

### 1f. LiCl 面板必须加注

LiCl 入选模型（Gradient Boosting）宏谱系 MdAPE=4.68%，但**整体 MdAPE=19.5%**（108/132 数据
集中在一个谱系）。在 LiCl 面板内加文字注释："入选 GB 整体 MdAPE = 19.5%"，否则会误导读者。

---

## 第 2 步：图 10B —— 专用 vs pooled 成对点图

1. 用 **长表**（8 行）：右键 **体系** 列 → `Set As → X`（并设为 Categorical）；右键 **宏MdAPE%** → `Set As → Y`；
2. 菜单 `Plot → Basic 2D → Scatter`；
3. 右键图 → `Plot Setup` → 把 **组别** 列拖到 **Group** 栏 → 点 Plot 或 Apply；
   此时"专用"与"pooled"点会分成两组（建议：专用=实心、pooled=空心）；
4. 连成对线：双击图 → Plot Details → 选中数据曲线 → **Line 页** → 勾选
   **Connect within Subgroup**（组内连线）→ OK。这样每个体系的两个点会自动连线；
5. 点旁标注 Δ 值：菜单 `Insert → Text` 手动加（NaCl −0.43、KCl −1.34、LiCl +2.08、CaCl₂ +0.97）；
   连线下降=专用更优，上升=pooled 更优；
6. 图注注明："pooled 对照为同折配对（训练=本体系训练折+其余三体系同折训练折，system 作 one-hot 特征），仅作比较、不作为 Agent 后端。"

---

## 第 3 步：统一美化与导出（两张图通用）

1. 双击轴 → Scale 页设范围与刻度；Title 页写轴标题（带单位）；字体建议 Arial 或 Times New Roman；
2. 配色：色盲友好（蓝/橙/灰系），全文体系颜色一致；不用 3D、饼图、截断柱状图；
3. 导出：`File → Export Graphs` → 选 **PDF**（矢量，用于投稿排版）或 TIFF（600 dpi，用于 Word 初稿）；
4. 图注必须包含：分析单位（642 条件中的该体系子集）、"谱系分组 5 折 CV（OOF）"、
   "误差条为折间范围非 CI"、"回顾性探索性、无独立外部验证"。

---

## 常见问题

- **中文列名乱码**：Import 时改用 `Data → Import from File → Import Wizard`，在编码步骤选 UTF-8；
- **点太挤/重叠**：Symbol 页把 Size 调小（如 9），或 Symbol 透明度 60%；
- **想让我代画**：如果你试了还是费劲，可以直接让我用 Python（matplotlib）按同样规范生成
  论文级图（PDF 矢量 + PNG），你再在 Origin 里微调或直接用。

## 图注草稿（中文，可直接改）

> **图 10 冻结数值后端的交叉验证性能。** A：四个溶液体系各自的六种候选数值模型在谱系分组
> 五折交叉验证下的宏谱系 MdAPE（选模主指标），误差条为五个测试折间的 MdAPE 范围而非统计置信区间，
> 实心点为按预先冻结规则选出的注册模型，灰色为 Dummy 中位数基线；LiCl 面板文字为该体系入选模型
> 在全部预测上的整体 MdAPE。B：各体系入选专用模型与 pooled 对照的宏谱系 MdAPE 成对比较
> （同折配对；pooled 训练含其余三体系同折数据）。全部结果为回顾性、探索性比较，无独立外部验证集。
