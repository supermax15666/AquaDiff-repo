# -*- coding: utf-8 -*-
"""Figure 15: deployment asset matrix and archived timing, approved option A.

All explanatory prose belongs in the manuscript caption. The figure has only
panel letters, essential column/row labels, axis labels, and measured values.
The local timing range and all archived values remain unchanged.
Run from the active figure folder without arguments, or provide --data-dir
when building a staged candidate.
"""
from pathlib import Path
import argparse, csv, json, os, sys
HERE=Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR', str(HERE/'.mplconfig'))
try:
    import matplotlib
except ModuleNotFoundError:
    for project_root in HERE.parents:
        candidate=project_root/'past_document'/'整理归档_20261002_130246'/'finalize_20261001'/'python_libs'
        if candidate.is_dir():
            sys.path.insert(0,str(candidate))
            break
    import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.ticker import LogLocator, NullFormatter

parser=argparse.ArgumentParser()
parser.add_argument('--data-dir', type=Path)
args=parser.parse_args()
DATA=args.data_dir or HERE/'data'
with (DATA/'图14B_成本延迟.csv').open(encoding='utf-8-sig', newline='') as stream:
    records=list(csv.DictReader(stream))
plt.rcParams.update({'font.family':'Arial','font.size':8.8,
                     'svg.fonttype':'none','pdf.fonttype':42,
                     'axes.linewidth':.65,'xtick.major.width':.65,
                     'ytick.major.width':.65,'savefig.bbox':None})

fig=plt.figure(figsize=(6.6,3.7),facecolor='white')
matrix=fig.add_axes([.012,.09,.52,.84])
matrix.set_xlim(0,9.3);matrix.set_ylim(-.15,5.1);matrix.axis('off')
names=['Local Base','SFT','Frozen ML','AquaDiff\n(4B)']
headers=['Base\nLLM','SFT\nLLM','DB','Frozen\nML','LLM\ncalls']
assets=[[True,False,False,False],[False,True,False,False],
        [False,False,False,True],[True,False,True,True]]
calls=['1','1','0','1 or 2']
for col,title in enumerate(headers):
    matrix.text(2.55+col*1.28+.575,4.73,title,ha='center',va='center',
                fontsize=8.8,color='#34444E',linespacing=1.08)
for row,label in enumerate(names):
    y=3.58-row*.99
    matrix.text(2.30,y+.405,label,ha='right',va='center',fontsize=8.8,
                weight='bold' if row==3 else 'normal',linespacing=1.08)
    for col in range(5):
        x=2.55+col*1.28
        if col<4:
            active=assets[row][col]
            face,textcol=('#E8EFF5','#365F7C') if active else ('#F1F3F5','#A4ADB4')
            value='\u2713' if active else '\u2014'
        else:
            value=calls[row]
            face,textcol=('#E1EEE5','#287A47') if row==2 else (
                ('#FAF0D7','#987500') if row==3 else ('#E8EFF5','#365F7C'))
        matrix.add_patch(Rectangle((x,y),1.15,.81,facecolor=face,edgecolor='none'))
        matrix.text(x+.575,y+.405,value,ha='center',va='center',color=textcol,
                    fontsize=9.5 if col==4 else 13,
                    weight='bold' if col==4 else 'normal',
                    fontfamily='Arial' if col==4 else 'DejaVu Sans')

groups=[
    ('Local direct', [r for r in records if '本地' in r['路径']], '#D55E00'),
    ('API', [r for r in records if 'API' in r['路径']], '#0072B2'),
    ('Frozen ML', [r for r in records if '冻结' in r['路径']], '#009E73'),
    ('AquaDiff\nmain', [r for r in records if '642主集' in r['条目']], '#8172B3'),
    ('AquaDiff\nexternal', [r for r in records if '外部' in r['条目']], '#8172B3'),
    ('AquaDiff\nchallenge', [r for r in records if '挑战' in r['条目']], '#8172B3'),
]
axis=fig.add_axes([.67,.16,.32,.71])
assert [len(group[1]) for group in groups]==[5,1,1,1,1,1]
timing_labels=[]
for row,(name,entries,color) in enumerate(groups):
    values=[]
    for entry in entries:
        raw=entry['延迟s/题(实测)'].strip()
        numeric=float(raw.lstrip('<'))
        values.append((numeric,raw))
        axis.barh(row,numeric,height=.52,color=color,edgecolor='none',alpha=.85,zorder=2)
    if len(values)>1:
        numbers=[v for v,_ in values]
        label=f'{min(numbers):.1f}\u2013{max(numbers):.1f}'
        position=max(numbers)*1.17
    else:
        number,label=values[0]
        position=number*1.17
    timing_labels.append(label)
    axis.text(position,row,label,va='center',ha='left',fontsize=9.3,
              color=color,weight='bold',clip_on=False)
assert timing_labels==['1.5\u20131.7','4.3','<0.01','2.00','2.57','1.25']
axis.set_xscale('log');axis.set_xlim(.004,60)
axis.set_ylim(-.6,5.6);axis.invert_yaxis()
axis.set_yticks(range(6));axis.set_yticklabels([g[0] for g in groups],fontsize=8.8)
axis.tick_params(axis='y',pad=5,length=3)
axis.set_xticks([.01,.1,1,10])
axis.xaxis.set_minor_formatter(NullFormatter())
axis.tick_params(axis='x',which='major',labelsize=8.8,length=3)
axis.tick_params(axis='x',which='minor',length=1.7,width=.45)
axis.set_xlabel('Time per task (s)',fontsize=8.8,labelpad=4)
axis.grid(axis='x',which='major',color='#DDDDDD',linewidth=.45,zorder=0)
axis.set_axisbelow(True)
fig.text(.013,.971,'(a)',ha='left',va='top',fontsize=11,weight='bold')
fig.text(.55,.971,'(b)',ha='left',va='top',fontsize=11,weight='bold')

fig.canvas.draw()
renderer=fig.canvas.get_renderer()
canvas=fig.bbox
texts=[text for text in fig.findobj(matplotlib.text.Text) if text.get_visible() and text.get_text()]
assert min(text.get_fontsize() for text in texts)>=8.8
outside=[]
for text in texts:
    box=text.get_window_extent(renderer)
    if box.x0<-.5 or box.y0<-.5 or box.x1>canvas.x1+.5 or box.y1>canvas.y1+.5:
        outside.append(text.get_text())
assert not outside, outside
stem=HERE/'图15_选型与成本'
for suffix in ['.png','.pdf','.svg','.tif']:
    options={'dpi':600,'facecolor':'white'}
    if suffix=='.tif':options['pil_kwargs']={'compression':'tiff_lzw'}
    fig.savefig(stem.with_suffix(suffix),**options)
plt.close(fig)
print(json.dumps({'figure':15,'width_in':6.6,'height_in':3.7,'minimum_font_pt':8.8,
                  'timing_labels':timing_labels,'explanatory_small_text':False,
                  'panel_letters_only':True,'outside_canvas_text':outside},ensure_ascii=True))
