"""Regenerate the native vector SVG from the current PowerPoint-exported PDF."""
from pathlib import Path
import sys
from xml.etree import ElementTree as ET

HERE=Path(__file__).resolve().parent
try:
    import pymupdf
except ModuleNotFoundError:
    for root in HERE.parents:
        libs=root/'past_document/整理归档_20261002_130246/finalize_20261001/python_libs'
        if libs.is_dir():
            sys.path.insert(0,str(libs))
            break
    import pymupdf

with pymupdf.open(HERE/'图14_路由轨迹.pdf') as doc:
    assert len(doc)==1 and not doc[0].get_images()
    svg=doc[0].get_svg_image(text_as_path=False)
tree=ET.fromstring(svg)
assert not tree.findall('.//{http://www.w3.org/2000/svg}image')
assert tree.findall('.//{http://www.w3.org/2000/svg}text')
(HERE/'图14_路由轨迹.svg').write_text(svg,encoding='utf-8')
print('Native vector SVG regenerated from current PDF')
