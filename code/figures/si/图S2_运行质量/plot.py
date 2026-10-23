# -*- coding: utf-8 -*-
"""补充图 S2 运行质量（A 臂五模型 + B 臂六模型）。
左：请求成功率 / schema 合法率 / 有效数值覆盖率（点图，11 模型 × 3 指标）
右：延迟分布（逐样本箱线图，对数轴）
数据源：CET_all/02_绘图数据_按图号/figS2_quality_A/B.csv、figS2_latency_A/B.csv
输出：图S2_运行质量.pdf / .png
"""
import os, sys, csv
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common_style import *  # noqa
FIGDATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
import matplotlib.pyplot as plt
import numpy as np

def load_q(fn):
    rows = []
    with open(os.path.join(FIGDATA, fn), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows

def load_lat(fn):
    d = {}
    with open(os.path.join(FIGDATA, fn), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["latency_seconds"].strip():
                d.setdefault(r["model"], []).append(float(r["latency_seconds"]))
    return d

qB = load_q("figS2_quality_B.csv"); qA = load_q("figS2_quality_A.csv")
lB = load_lat("figS2_latency_B.csv"); lA = load_lat("figS2_latency_A.csv")

# 模型顺序：B 臂（图 5 序）在上，A 臂在下
order = [r["model"] for r in sorted(qB, key=lambda r: -float(r["valid_numeric_percent"]))]
order += [r["model"] for r in sorted(qA, key=lambda r: -float(r["valid_numeric_percent"]))]
qmap = {r["model"]: r for r in qB + qA}
lmap = {**lB, **lA}

fig, (axL, axR) = plt.subplots(1, 2, figsize=(DOUBLE, 3.2),
                               gridspec_kw=dict(left=0.20, right=0.99, top=0.88, bottom=0.19,
                                                wspace=0.45))
ys = np.arange(len(order))[::-1]
# 左：三项质量指标
for y, m in zip(ys, order):
    r = qmap[m]
    c = model_color(m)
    axL.plot(float(r["request_success_percent"]), y, "o", color=c, ms=4.0)
    axL.plot(float(r["schema_valid_percent"]), y, "s", color=c, mfc="white", mec=c, mew=0.9, ms=3.6)
    axL.plot(float(r["valid_numeric_percent"]), y, "^", color=c, ms=4.2)
    axL.text(float(r["valid_numeric_percent"]) - 0.9, y + 0.26,
             min(float(r["valid_numeric_percent"]), float(r["request_success_percent"]),
                 float(r["schema_valid_percent"])) and "%.1f" % min(float(r["valid_numeric_percent"]),
                 float(r["request_success_percent"]), float(r["schema_valid_percent"])) or "",
             fontsize=5.0, color=c, ha="right")
axL.set_yticks(ys); axL.set_yticklabels([model_display(m) for m in order], fontsize=6.0)
axL.set_xlim(97.5, 100.6)
axL.set_xticks([98, 99, 100])
axL.set_xlabel("Percentage (%)")
axL.set_title("Request success / schema validity / valid-numeric coverage", fontsize=6.8, loc="left")
panel_label(axL, "A", x=-0.30, y=1.10)
from matplotlib.lines import Line2D
hL = [Line2D([0], [0], marker="o", color=BLACK, mfc=BLACK, ms=3.8, lw=0, label="request success"),
      Line2D([0], [0], marker="s", color=BLACK, mfc="white", ms=3.4, lw=0, label="schema validity"),
      Line2D([0], [0], marker="^", color=BLACK, mfc=BLACK, ms=3.8, lw=0, label="valid-numeric coverage")]
axL.legend(handles=hL, loc="lower left", fontsize=5.2)

# 右：延迟箱线（对数）
data = [lmap[m] for m in order]
bp = axR.boxplot(data, orientation="horizontal", widths=0.55, patch_artist=True, showfliers=False,
                 medianprops=dict(color=BLACK, lw=0.8),
                 boxprops=dict(lw=0.6), whiskerprops=dict(lw=0.6), capprops=dict(lw=0.6))
for patch, m in zip(bp["boxes"], order):
    patch.set_facecolor(model_color(m)); patch.set_alpha(0.55)
axR.set_yticklabels([]); axR.invert_yaxis()
axR.set_xscale("log")
axR.set_xlabel("Per-call latency (s, log scale; per sample)")
axR.set_title("Latency distribution", fontsize=6.8, loc="left")
panel_label(axR, "B", x=-0.14, y=1.10)
fig.text(0.5, 0.022, "Top 6 rows: Arm B (API via a remote gateway; latency includes network overhead); bottom 5 rows: Arm A (local CPU inference, main-comparison runs). Latency is an infrastructure metric, not a model-knowledge result",
         fontsize=5.0, color="#555555", ha="center")
save(fig, "图S2_运行质量", __file__)
