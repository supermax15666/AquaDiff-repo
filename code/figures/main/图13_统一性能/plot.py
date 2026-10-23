# -*- coding: utf-8 -*-
"""Figure 13: frozen 48/64-question accuracy and audited numerical configuration.

Journal Figure 13 A layout, 2026-10-03. Visual revision only: shared method row
labels, paired bars and filled-cell matrix. No qualitative capability scoring.

Run in the current figure directory: python plot.py
Run while staged: python plot.py --data-dir <current figure directory>/data
All outputs are saved alongside this script unless --output-dir is provided.
The source CSV is read only. SVG retains native editable text and vectors.
"""
from pathlib import Path
import argparse
import csv
import os
import sys

HERE = Path(__file__).resolve().parent
# The project already archives its Python 3.12 plotting dependencies. This
# read-only fallback lets the bundled runtime redraw a copied script unchanged.
os.environ.setdefault('MPLCONFIGDIR', str(HERE / '.mplconfig'))
try:
    import matplotlib
except ModuleNotFoundError:
    for project_root in HERE.parents:
        candidate = project_root / 'past_document' / '整理归档_20261002_130246' / 'finalize_20261001' / 'python_libs'
        if candidate.is_dir():
            sys.path.insert(0, str(candidate))
            break
    import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Rectangle
import numpy as np

plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Arial', 'Liberation Sans', 'DejaVu Sans'],
    'font.size': 8.8,
    'axes.labelsize': 9.0,
    'xtick.labelsize': 8.8,
    'ytick.labelsize': 9.0,
    'axes.linewidth': .6,
    'axes.unicode_minus': False,
    'svg.fonttype': 'none',
    'pdf.fonttype': 42,
    'savefig.bbox': None,
    'savefig.pad_inches': 0,
})

NAME = '图13_统一性能'
WIDTH, HEIGHT = 6.6, 3.4
DARK, PALE = '#2B5F95', '#A8C8E8'
GREEN = ('#E1EEE5', '#287A47')
AMBER = ('#FAF0D7', '#987500')
RED = ('#F8E3DF', '#AD4942')
SOURCE = ('#E8EFF5', '#365F7C')
AUDITED = {
    'Closed-book (5 models)': ('Base\n(5 models)', 'Closed-book', '100%', '0/16'),
    'SFT (5 models)': ('SFT\n(5 models)', 'Fine-tuned', '100%', '0/16'),
    'Frozen ML': ('Frozen ML', 'ML', '75%', '16/16'),
    'AquaDiff (4B)': ('AquaDiff\n(4B)', 'DB or ML', '75%', '16/16'),
}


def read_data(data_dir):
    path = Path(data_dir) / 'fig12_panel_data.csv'
    with path.open(encoding='utf-8-sig', newline='') as f:
        rows = [(r['path'], float(r['in_domain_48q_pct']),
                 float(r['full_set_64q_pct'])) for r in csv.DictReader(f)]
    assert [r[0] for r in rows] == list(AUDITED), 'Unexpected method order in frozen CSV'
    return rows


def build_figure(rows):
    fig = plt.figure(figsize=(WIDTH, HEIGHT), dpi=200)
    # Two plots share the same exact vertical geometry and method row centers.
    bottom, plot_height = .55 / HEIGHT, 2.20 / HEIGHT
    ax = fig.add_axes([1.08 / WIDTH, bottom, 2.36 / WIDTH, plot_height])
    matrix = fig.add_axes([3.68 / WIDTH, bottom, 2.77 / WIDTH, plot_height])
    ys = np.arange(4)[::-1]
    for y, (method, indomain, fullset) in zip(ys, rows):
        ax.barh(y + .15, indomain, height=.25, color=DARK, edgecolor='none', zorder=3)
        ax.barh(y - .15, fullset, height=.25, color=PALE, edgecolor='none', zorder=3)
        ax.text(indomain + 2.4, y + .15, f'{indomain:.1f}', ha='left', va='center',
                fontsize=9.2, color=DARK, fontweight='bold')
        ax.text(fullset + 2.4, y - .15, f'{fullset:.1f}', ha='left', va='center',
                fontsize=9.2, color='#537697')
    ax.set_yticks(ys)
    labels = ax.set_yticklabels([AUDITED[r[0]][0] for r in rows], fontsize=9.0, linespacing=1.1)
    labels[-1].set_fontweight('bold')
    ax.tick_params(axis='y', length=0, pad=8)
    ax.tick_params(axis='x', width=.6, length=3, pad=4, labelsize=8.8)
    ax.set_xlim(0, 116)
    ax.set_ylim(-.65, 3.55)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.set_xlabel('Macro-system Acc@10% (%)', fontsize=9.0, labelpad=7)
    ax.grid(axis='x', linewidth=.45, color='#E1E4E6')
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_linewidth(.6)
        spine.set_color('#666666')
    handles = [Patch(facecolor=DARK, edgecolor='none', label='In-domain (48 q)'),
               Patch(facecolor=PALE, edgecolor='none', label='Full set (64 q)')]
    fig.legend(handles=handles, loc='upper left', bbox_to_anchor=(1.07 / WIDTH, 3.05 / HEIGHT),
               ncol=2, fontsize=8.8, frameon=False, handlelength=1.05, handletextpad=.4,
               columnspacing=.8, borderaxespad=0)

    matrix.set_xlim(0, 3)
    matrix.set_ylim(-.65, 3.55)
    matrix.set_axis_off()
    # Rectangles have uniform dimensions and white gutters; no table rules.
    cell_w, cell_h = .90, .81
    for i, (method, _, _) in enumerate(rows):
        yc = ys[i]
        _, source, coverage, refusal = AUDITED[method]
        for j, value in enumerate([source, coverage, refusal]):
            fill, ink = SOURCE if j == 0 else (GREEN if value in ['100%', '16/16'] else AMBER if value == '75%' else RED)
            matrix.add_patch(Rectangle((j + .05, yc - cell_h / 2), cell_w, cell_h,
                                      facecolor=fill, edgecolor='none'))
            matrix.text(j + .50, yc, value, ha='center', va='center', color=ink,
                        fontsize=9.0 if j == 0 else 10.0,
                        fontweight='normal' if j == 0 else 'bold')
    headers = ['Numerical\nsource', 'Coverage\n(64 q)', 'OOD refusal\n(16 q)']
    for j, header in enumerate(headers):
        # Center headers above the shared row area rather than inside plot data.
        fig.text((3.68 + (j + .5) * 2.77 / 3) / WIDTH, 3.00 / HEIGHT,
                 header, ha='center', va='center', fontsize=9.0,
                 color='#303030', linespacing=1.1)
    fig.text(.15 / WIDTH, 3.25 / HEIGHT, '(a)', fontsize=11, fontweight='bold', ha='left', va='top')
    fig.text(3.68 / WIDTH, 3.25 / HEIGHT, '(b)', fontsize=11, fontweight='bold', ha='left', va='top')
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=HERE / 'data')
    parser.add_argument('--output-dir', type=Path, default=HERE)
    args = parser.parse_args()
    rows = read_data(args.data_dir)
    fig = build_figure(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for ext in ['png', 'pdf', 'svg', 'tif']:
        kwargs = {'dpi': 600, 'bbox_inches': None, 'facecolor': 'white'}
        if ext == 'tif':
            kwargs['pil_kwargs'] = {'compression': 'tiff_lzw'}
        fig.savefig(args.output_dir / f'{NAME}.{ext}', **kwargs)
    print(f'Figure 13: {WIDTH} x {HEIGHT} in; PNG/TIF 600 dpi; all normal text >= 8.8 pt')
    print('Frozen bar values:', [(r[0], r[1], r[2]) for r in rows])


if __name__ == '__main__':
    main()
