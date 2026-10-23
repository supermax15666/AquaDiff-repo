# -*- coding: utf-8 -*-
"""Extract text from the 9 downloaded candidate PDFs into _text/*.txt."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "py" / "微调" / ".pdf_tools"))

from pypdf import PdfReader  # noqa: E402

PDF_DIR = ROOT / "py" / "微调" / "外部数据来源"
OUT_DIR = PDF_DIR / "_text"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(PDF_DIR.glob("*.pdf")):
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(f"===== PAGE {i + 1} =====\n{pages[i]}" for i in range(len(pages)))
        out = OUT_DIR / (path.stem + ".txt")
        out.write_text(text, encoding="utf-8")
        print(f"{path.name}: {len(reader.pages)} pages -> {out.name} ({len(text)} chars)")


if __name__ == "__main__":
    main()
