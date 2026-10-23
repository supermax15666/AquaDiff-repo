# -*- coding: utf-8 -*-
"""Probe: does the loaded model return reasoning_tokens (thinking on)?

Usage: python probe_thinking.py [model_id] [max_tokens]
Default model_id: qwen3-8b-instruct@q4_k_m; default max_tokens: 256
"""
import json
import sys
import urllib.request

URL = "http://192.168.2.100:1234/v1/chat/completions"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3-8b-instruct@q4_k_m"
MAX_TOKENS = int(sys.argv[2]) if len(sys.argv) > 2 else 256


def probe(name: str, extra: dict) -> None:
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a benchmark assistant. Return only valid JSON."},
            {
                "role": "user",
                "content": (
                    "Predict the mutual diffusion coefficient of NaCl-H2O at T = 298.15 K "
                    "and c = 1.000000 mol/L. Return the multiplier x where D = x * 10^-9 "
                    'm^2/s. Return JSON: {"diffusion_1e9_m2_s": x}'
                ),
            },
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": 0,
    }
    body.update(extra)
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read())
        choice = data["choices"][0]
        msg = choice.get("message") or {}
        print(f"[{name}] model={MODEL} max_tokens={MAX_TOKENS} finish={choice.get('finish_reason')} "
              f"usage={data.get('usage')} "
              f"reasoning_len={len(msg.get('reasoning_content') or '')} "
              f"content={msg.get('content')!r}"[:600])
    except Exception as exc:
        print(f"[{name}] ERROR: {exc}")


if __name__ == "__main__":
    probe("enable_thinking=false", {"enable_thinking": False})
    probe("chat_template_kwargs", {"chat_template_kwargs": {"enable_thinking": False}})
