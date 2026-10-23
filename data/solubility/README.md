# 08_各体系溶液溶解度数据 —— E 臂饱和安全层的数据与来源（2026-08-27 归档）

> 用途：方案 v2.15/v2.16 §3.E 第 3 步——c > c_sat(T)·1.01 时明示并按饱和浓度夹取。
> 冻结产物：`..\..\py\E_Agent\frozen\solubility_frozen.json`（48 条 canonical 记录，
> records_content_sha256 `b7d40c4f…`；含完整复核与验证记录）。
> 本目录 = 数据正本 + 文献来源 + 收集过程归档。

## 内容

| 文件/目录 | 说明 |
|---|---|
| `溶解度录入_CRC92_v2.xlsx / .csv` | **最终表**（48 行：四体系 × 12 个 CRC 原生温度点，wt% + 密度换算 c_sat_mol_L + 固相 + 逐行来源）；SHA-256 `56861c82…` |
| `密度待填表.csv` | 密度中间表（48 行，N&S 1988 / Conde 2004 计算值与逐行常数引用） |
| `溶解度收集日志.md` | 完整数据链日志（§1–§8：CRC 提取、保真度验证、固相分段、密度源三轮核验、取舍记录） |
| `草稿_v1\` | v1 草稿（c_sat 留空的中间版本，留档） |
| `文献_采用\` | novotny1988.pdf（NaCl/KCl/LiCl 密度方程）、conde2004.pdf（CaCl₂ 密度方程）、clynne1979.pdf（CaCl₂/LiCl 溶解度黄金验证 + LiCl 固相修正）、CaCl数据-LoBo.pdf（Bogatykh 表交叉验证，用户纸质手册扫描） |
| `文献_已排除\` | je00038a004.pdf（Söhnel 1984，18 种物质不含四体系）、10.1135@cccc19832327.pdf（1983 CCC 估算论文无 CaCl₂）——排除理由见日志 §6 |
| `归档_收集过程\` | 收集交接提示词、密度需求清单（已被日志 §6 取代）、空白录入模板 |

**主源 CRC Handbook 92nd ed.（溶解度表 5-190–5-195）未重复拷贝**：与
`02_数据\03_外部前瞻集_64题冻结\文献原件\CRC Handbook…92nd Edition(科研通-ablesci.com).pdf`
为同哈希同一文件（2026-08-27 校验一致）。

## 数据链一句话

溶解度单源 CRC 92 表 5-190（wt%，行引 IUPAC SDS 47 / Potter & Clynne）→ 密度：NaCl/KCl/LiCl 用
Novotný & Söhnel 1988 Eq.1 常数自洽求解（vs CRC/Perry 锚点残差 ≤1.8 kg/m³）、CaCl₂ 用 Conde 2004
方程（适用域 ξ≤0.60 全覆盖，Bogatykh 117 点/Perry/LiCl 侧三重验证）→ c_sat = 1000·ρ·w₂/M₂。
交叉验证：NaCl/KCl/LiCl vs Apelblat ≤0.08%；CaCl₂ vs C&P 1979 原始测量 ≤0.08%。
主对话独立复核（N&S/Conde 方程重算 48 行）全部一致，3 个 NaCl 低温段微降警告确认为真实物理行为。

> 注：`solubility_frozen.json` 的 manifest 记录的源文件路径（py\E_Agent\…）为冻结时位置；
> 2026-08-27 分区清理后正本移至本目录，哈希不变。
