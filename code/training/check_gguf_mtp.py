# -*- coding: utf-8 -*-
"""检查 GGUF 文件是否包含 MTP（blk.64）张量——判断 Base 与 SFT 转换命令是否一致。

用法（在服务器上运行，GGUF 文件都在服务器 E: 盘）：
  python check_gguf_mtp.py <gguf路径1> [gguf路径2] ...
示例：
  python check_gguf_mtp.py E:\gguf\cet_formal\qwen3.6-27b-Q4_K_M.gguf E:\gguf\cet_sft\qwen3.6-27b-lora-r64-q4_k_m.gguf
原理：GGUF 张量名以明文存储在文件内，分块流式扫描（不会把 15GB 全部读进内存）。
"""
from __future__ import annotations

import sys

BLOCK = 1024 * 1024


def scan(path: str) -> tuple[int, bool, bool]:
    total = 0
    found_blk64 = False
    found_mtp = False
    with open(path, "rb") as handle:
        while True:
            block = handle.read(BLOCK)
            if not block:
                break
            total += len(block)
            if b"blk.64" in block:
                found_blk64 = True
            if b"mtp" in block.lower():
                found_mtp = True
    return total, found_blk64, found_mtp


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    for path in sys.argv[1:]:
        size, blk64, mtp = scan(path)
        name = path.replace("\\", "/").split("/")[-1]
        print(f"{name} | size={size/1e9:.1f} GB | blk.64: {blk64} | mtp: {mtp}")
        print(f"  -> 判断: {'含 MTP 头' if blk64 else '无 MTP 头（--no-mtp 或等效）'}")
    if len(sys.argv) < 2:
        print("用法: python check_gguf_mtp.py <gguf1> [gguf2] ...")


if __name__ == "__main__":
    main()
