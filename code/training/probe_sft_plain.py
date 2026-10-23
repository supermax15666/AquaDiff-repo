# -*- coding: utf-8 -*-
"""SFT 27B 部署探测：普通请求（不带任何 thinking 参数）验证 Reasoning 是否关闭。

用法（本地即可，能访问服务器 1234 端口）：
  python probe_sft_plain.py [--base-url http://192.168.2.100:1234/v1] [--model qwen3.6-27b-lora-r64]
判定标准：
  reasoning_tokens == 0 且 content 非空  -> 通过
  reasoning_tokens > 0 或 content 为空    -> 思考未关/耗尽 token，需在 LM Studio 设置 Reasoning=Off
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://192.168.2.100:1234/v1")
    parser.add_argument("--model", default="qwen3.6-27b-lora-r64")
    args = parser.parse_args()

    payload = {
        "model": args.model,
        "messages": [
            {"role": "user", "content": "What is 2+2? Reply with only the number."}
        ],
        "max_tokens": 64,
        "temperature": 0,
        "top_p": 1.0,
    }
    request = urllib.request.Request(
        args.base_url + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print("HTTP", exc.code, exc.read().decode("utf-8", errors="replace")[:500])
        return
    choice = body["choices"][0]
    content = choice["message"].get("content")
    reasoning = choice["message"].get("reasoning_content")
    usage = body.get("usage", {})
    details = usage.get("completion_tokens_details", {})
    reasoning_tokens = details.get("reasoning_tokens", 0)
    print("model:", body.get("model"))
    print("content:", repr(content))
    print("reasoning_content:", repr(reasoning))
    print("reasoning_tokens:", reasoning_tokens)
    print("finish_reason:", choice.get("finish_reason"))
    if reasoning_tokens == 0 and content:
        print("VERDICT: PASS (nothink, content ok)")
    else:
        print("VERDICT: FAIL (thinking still on or content empty) -> set LM Studio Reasoning=Off and reload")


if __name__ == "__main__":
    main()
