# -*- coding: utf-8 -*-
"""在整本 CRC Handbook PDF 中定位 KCl 溶液密度表所在页。

逐页提取文本，记录含以下关键词的页号：
- "Concentrative Properties"（章节标题页）
- "Potassium chloride" 且同页含密度特征（"density"/"Density"）
把匹配页的文本写入 _text/crc_matched_pages.txt 供后续读值。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "py" / "微调" / ".pdf_tools"))

from pypdf import PdfReader  # noqa: E402

PDF = ROOT / "py" / "微调" / "外部数据来源" / "CRC Handbook of Chemistry and Physics, 92nd Edition(科研通-ablesci.com).pdf"
OUT = ROOT / "py" / "微调" / "外部数据来源" / "_text" / "crc_matched_pages.txt"


def main() -> None:
    reader = PdfReader(str(PDF))
    total = len(reader.pages)
    print(f"total pages: {total}", flush=True)
    matches: list[str] = []
    for index, page in enumerate(reader.pages):
        if index % 200 == 0:
            print(f"scanning page {index}/{total}", flush=True)
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            print(f"page {index}: extract error {exc}", flush=True)
            continue
        low = text.lower()
        hit = False
        tags: list[str] = []
        if "concentrative properties" in low:
            tags.append("SECTION")
            hit = True
        if "potassium chloride" in low and "density" in low:
            tags.append("KCL_DENSITY")
            hit = True
        if hit:
            matches.append(f"===== PDF PAGE INDEX {index} tags={','.join(tags)} =====\n{text}\n")
            print(f"page {index}: {','.join(tags)}", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(matches), encoding="utf-8")
    print(f"done; matched pages written to {OUT}", flush=True)


if __name__ == "__main__":
    main()
