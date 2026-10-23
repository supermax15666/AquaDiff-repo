# ---------------------------------------------------------------------------
# NOTE (added 2026-10-14): the OUTPUT file names below were updated to the
# current figure numbers of the manuscript. The inline comments and local
# variable names ($fig4, $fig8B, ...) still use the ORIGINAL numbers of this
# script as it was written in 2026-08. The full old -> new mapping is recorded
# in  原始数据与分析脚本\09_共享_绘图数据\文件对照_旧名到当前图号.md
# The $d02 / $d01 / $out paths point at the original CET working tree, not at
# this archive; this file is kept as the historical generator.
# ---------------------------------------------------------------------------
﻿# prep_plot_tables.ps1 - ASCII only. Builds minimal per-figure plotting CSVs from 02 data.
$ErrorActionPreference = "Stop"

$d02 = "C:\Users\AS\Desktop\CET\paper_draft\data\02_绘图数据"
$d01 = "C:\Users\AS\Desktop\CET\paper_draft\data\01_原始分析结果"
$out = "C:\Users\AS\Desktop\CET\paper_draft\data\03_最小绘图表"
New-Item -ItemType Directory -Path $out -Force | Out-Null
$enc = New-Object System.Text.UTF8Encoding($false)

function W($name, $lines) {
  $path = Join-Path $out $name
  [System.IO.File]::WriteAllLines($path, $lines, $enc)
}
# NOTE: the old guard `($v -eq "")` silently swallowed legitimate zeros
# (in PowerShell, `0 -eq ""` is True because "" coerces to 0), which blanked
# 13 (Arm B) + 4 (Arm A) exact-zero signed errors in fig8B and the 0.0%
# cells in fig6. Use IsNullOrEmpty on the string form instead.
function Pct($v) {
  if ($null -eq $v -or [string]::IsNullOrEmpty([string]$v)) { return "" }
  try { return [math]::Round([double]$v * 100, 1) } catch { return "" }
}
function Rnd($v, $d) {
  if ($null -eq $v -or [string]::IsNullOrEmpty([string]$v)) { return "" }
  try { return [math]::Round([double]$v, $d) } catch { return "" }
}
function Median($arr) {
  $s = @($arr | Sort-Object)
  if ($s.Count -eq 0) { return "" }
  if ($s.Count % 2 -eq 1) { return $s[[int](($s.Count - 1) / 2)] }
  return ([double]$s[[int]($s.Count / 2 - 1)] + [double]$s[[int]($s.Count / 2)]) / 2
}

# fig1 / fig2 static stats
W "表1_数据集统计.csv" @(
  "system,n_records,n_lineages,n_unique_conditions,n_main_questions,n_sensitivity_questions",
  "NaCl-H2O,256,16,TBD,174,60",
  "KCl-H2O,268,16,TBD,247,60",
  "LiCl-H2O,152,6,TBD,132,60",
  "CaCl2-H2O,109,7,TBD,89,60",
  "total,785,45,696,642,240"
)

$bpB = Import-Csv (Join-Path $d02 "源数据_题目级_B臂.csv") -Encoding UTF8
$bpA = Import-Csv (Join-Path $d02 "源数据_题目级_A臂.csv") -Encoding UTF8

# fig4 T-c coverage (one row per question)
$fig4 = @("system,temperature_K,concentration_mol_L,lineage")
$bpB | Group-Object question_id | ForEach-Object { $_.Group[0] } |
  Sort-Object system, { [double]$_.temperature_K }, { [double]$_.concentration_mol_L } |
  ForEach-Object { $fig4 += "{0},{1},{2},{3}" -f $_.system, $_.temperature_K, $_.concentration_mol_L, $_.origin_lineage_id }
W "图2_温度浓度覆盖.csv" $fig4

# fig5A / fig5B model-level point-CI
function Fig5($src, $name) {
  $m = Import-Csv $src -Encoding UTF8
  $rows = @("model,view,acc10_macro_percent,ci_low_percent,ci_high_percent")
  foreach ($r in $m) {
    $rows += "{0},{1},{2},{3},{4}" -f $r.model_key, $r.analysis_set_role, (Pct $r.macro_system_accuracy_10pct), (Pct $r.macro_system_accuracy_10pct_ci95_low), (Pct $r.macro_system_accuracy_10pct_ci95_high)
  }
  W $name $rows
}
Fig5 (Join-Path $d02 "源数据_图5_B臂模型指标.csv") "图5a_闭卷CI_B臂.csv"
Fig5 (Join-Path $d02 "源数据_图5_A臂模型指标.csv") "图5b_闭卷CI_A臂.csv"

# fig6 heatmap
function Heatmap($bp, $name) {
  $rows = @("model,system,acc10_mean_percent")
  $bp | Group-Object { $_.model_key + "|" + $_.system } | Sort-Object Name | ForEach-Object {
    $avg = ($_.Group | Measure-Object -Property accuracy_10pct_fraction -Average).Average
    $parts = $_.Name.Split("|")
    $rows += "{0},{1},{2}" -f $parts[0], $parts[1], (Pct $avg)
  }
  W $name $rows
}
Heatmap $bpB "图6_热图_B臂.csv"
Heatmap $bpA "图6_热图_A臂.csv"

# fig7 scatter
function Scatter($bp, $name) {
  $rows = @("model,system,observed,predicted_median")
  $bp | ForEach-Object { $rows += "{0},{1},{2},{3}" -f $_.model_key, $_.system, $_.observed_diffusion_1e9_m2_s, $_.predicted_median_1e9_m2_s }
  W $name $rows
}
Scatter $bpB "图7_观测预测散点_B臂.csv"
Scatter $bpA "图8_观测预测散点_A臂.csv"

# fig8A ecdf (sorted by APE within model)
function Ecdf($bp, $name) {
  $rows = @("model,ape_median_percent")
  $bp | Sort-Object model_key, { [double]$_.absolute_percentage_error_median } | ForEach-Object {
    $rows += "{0},{1}" -f $_.model_key, $_.absolute_percentage_error_median
  }
  W $name $rows
}
Ecdf $bpB "图9a_APE累积_B臂.csv"
Ecdf $bpA "图9a_APE累积_A臂.csv"

# fig8B signed error
function SignedErr($bp, $name) {
  $rows = @("model,system,signed_error")
  $bp | ForEach-Object {
    $se = [double]$_.predicted_median_1e9_m2_s - [double]$_.observed_diffusion_1e9_m2_s
    $rows += "{0},{1},{2}" -f $_.model_key, $_.system, (Rnd $se 4)
  }
  W $name $rows
}
SignedErr $bpB "图9b_带符号误差_B臂.csv"
SignedErr $bpA "图9b_带符号误差_A臂.csv"

# figS1 stability
function Stab($bp, $name) {
  $rows = @("model,system,predicted_range")
  $bp | ForEach-Object { $rows += "{0},{1},{2}" -f $_.model_key, $_.system, $_.predicted_range_1e9_m2_s }
  W $name $rows
}
Stab $bpB "图S1_重复稳定性_B臂.csv"
Stab $bpA "图S1_重复稳定性_A臂.csv"

# figS2 quality + latency
$slB = Import-Csv (Join-Path $d02 "源数据_逐次调用_B臂.csv") -Encoding UTF8
$slA = Import-Csv (Join-Path $d02 "源数据_逐次调用_A臂.csv") -Encoding UTF8
function Quality($sl, $name) {
  $rows = @("model,request_success_percent,schema_valid_percent,valid_numeric_percent,latency_median_s")
  $sl | Group-Object model_key | Sort-Object Name | ForEach-Object {
    $g = $_.Group
    $rs = ($g | ForEach-Object { if ($_.request_success -eq "True") { 1 } else { 0 } } | Measure-Object -Average).Average
    $sv = ($g | ForEach-Object { if ($_.answer_schema_valid -eq "True") { 1 } else { 0 } } | Measure-Object -Average).Average
    $vn = ($g | ForEach-Object { if ($_.valid_numeric_response -eq "True") { 1 } else { 0 } } | Measure-Object -Average).Average
    $lt = Median ($g | ForEach-Object { [double]$_.latency_seconds_final_attempt })
    $rows += "{0},{1},{2},{3},{4}" -f $_.Name, (Pct $rs), (Pct $sv), (Pct $vn), (Rnd $lt 2)
  }
  W $name $rows
  $rows2 = @("model,latency_seconds")
  $sl | ForEach-Object { $rows2 += "{0},{1}" -f $_.model_key, $_.latency_seconds_final_attempt }
  $name2 = $name -replace "quality", "latency"
  W $name2 $rows2
}
Quality $slB "图S2a_运行质量_B臂.csv"
Quality $slA "图S2a_运行质量_A臂.csv"

# fig9 examples
$rowsU = @("model,unique_predictions")
foreach ($bp in @($bpB, $bpA)) {
  $bp | Group-Object model_key | Sort-Object Name | ForEach-Object {
    $u = @($_.Group | Where-Object { $_.predicted_median_1e9_m2_s -ne "" } | ForEach-Object { $_.predicted_median_1e9_m2_s } | Sort-Object -Unique)
    $rowsU += "{0},{1}" -f $_.Name, $u.Count
  }
}
W "图10a_唯一预测值数.csv" $rowsU
$rowsX = @("type,model,question_id,system,temperature_K,concentration_mol_L,observed,predicted_median,ape_percent,note")
$bpB | Sort-Object { [double]$_.absolute_percentage_error_median } -Descending | Select-Object -First 6 | ForEach-Object {
  $rowsX += "tail_error,{0},{1},{2},{3},{4},{5},{6},{7},top APE sample" -f $_.model_key, $_.question_id, $_.system, $_.temperature_K, $_.concentration_mol_L, $_.observed_diffusion_1e9_m2_s, $_.predicted_median_1e9_m2_s, $_.absolute_percentage_error_median
}
$slB | Where-Object { $_.valid_numeric_response -eq "False" } | Select-Object -First 3 | ForEach-Object {
  $rowsX += "parse_or_format_failure,{0},{1},{2},{3},{4},,,,parse failure sample" -f $_.model_key, $_.question_id, $_.system, $_.temperature_K, $_.concentration_mol_L
}
W "图10_错误示例.csv" $rowsX

# fig4.2 thinking sensitivity metrics
$tm = Import-Csv (Join-Path $d01 "A臂_thinking敏感性_27B_240题\manuscript_model_metrics.csv") -Encoding UTF8
$rowsT = @("view,acc10_percent,ci_low_percent,ci_high_percent,acc5_percent,mae,mdape_percent,r2")
foreach ($r in $tm) {
  $rowsT += "{0},{1},{2},{3},{4},{5},{6},{7}" -f $r.analysis_set_role, (Pct $r.macro_system_accuracy_10pct), (Pct $r.macro_system_accuracy_10pct_ci95_low), (Pct $r.macro_system_accuracy_10pct_ci95_high), (Pct $r.macro_system_accuracy_5pct), $r.mae_valid_numeric_1e9_m2_s, $r.mdape_valid_numeric_percent, $r.r_squared_valid_numeric
}
W "表S27_思考敏感性指标.csv" $rowsT

# fig11 copies
Copy-Item (Join-Path $d02 "图11_D臂_面板数据_专用模型.csv") (Join-Path $out "图12a_选模面板.csv")
Copy-Item (Join-Path $d02 "图11_D臂_专用vs_pooled.csv") (Join-Path $out "图12b_专用vs合并_宽表.csv")
Copy-Item (Join-Path $d02 "图11_D臂_专用vs_pooled_长表.csv") (Join-Path $out "图12b_专用vs合并_长表.csv")
Copy-Item (Join-Path $d02 "图11_D臂_冻结汇总_权威数字.csv") (Join-Path $out "图12_冻结汇总_权威数字.csv")

Write-Output "done"
