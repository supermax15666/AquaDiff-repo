# -*- coding: utf-8 -*-
"""Fig. 5 Temperature-concentration coverage of the 642-question main set (2x2 panels).
Data: CET_all/02_绘图数据_按图号/fig4_coverage.csv (642 questions).
(v6: single colour per panel — per-lineage colouring and its 40-entry legends moved out;
lineage composition is in supplementary Fig. S3. Do not connect discrete literature points.)
Output: 图5_覆盖图.pdf / .png
"""
import os, sys, csv
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common_style import *  # noqa
FIGDATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

rows = []
with open(os.path.join(FIGDATA, "fig4_coverage.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        rows.append((r["system"], float(r["temperature_K"]), float(r["concentration_mol_L"])))

SYS_KEYS = ["NaCl-H2O", "KCl-H2O", "LiCl-H2O", "CaCl2-H2O"]

fig, axes = plt.subplots(2, 2, figsize=(DOUBLE, 3.6),
                         gridspec_kw=dict(left=0.075, right=0.99, top=0.94, bottom=0.10,
                                          hspace=0.42, wspace=0.24))
for idx, (sk, ax) in enumerate(zip(SYS_KEYS, axes.flat)):
    sub = [r for r in rows if r[0] == sk]
    ax.scatter([r[2] for r in sub], [r[1] for r in sub], s=8,
               color=sys_color(sk), edgecolors="none", zorder=3, alpha=0.8)
    ax.set_xscale("log")
    ax.set_xlim(0.0015, 12)
    ax.set_xticks([0.001, 0.01, 0.1, 1, 10])
    ax.set_xticklabels(["0.001", "0.01", "0.1", "1", "10"])
    ax.xaxis.set_minor_formatter(mticker.NullFormatter())
    ax.set_ylim(265, 330)
    ax.set_yticks([273.15, 283.15, 293.15, 303.15, 313.15, 323.15])
    ax.set_yticklabels(["273", "283", "293", "303", "313", "323"])
    ax.set_title(sys_display(sk), fontsize=7.5)
    ax.set_xlabel("Concentration c (mol/L, log scale)" if idx >= 2 else "")
    ax.set_ylabel("Temperature T (K)" if idx % 2 == 0 else "")
    panel_label(ax, chr(65 + idx), x=-0.16, y=1.04)

save(fig, "图4_覆盖图", __file__)
