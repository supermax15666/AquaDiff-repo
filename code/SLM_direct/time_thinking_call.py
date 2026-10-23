# -*- coding: utf-8 -*-
"""Time one thinking-mode call for latency estimation."""
import json
import time
import urllib.request

body = {
    "model": "qwen3.6-27b@q4_k_m",
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
    "max_tokens": 4096,
    "temperature": 0,
}
req = urllib.request.Request(
    "http://192.168.2.100:1234/v1/chat/completions",
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
t0 = time.time()
with urllib.request.urlopen(req, timeout=600) as resp:
    data = json.loads(resp.read())
dt = time.time() - t0
usage = data.get("usage") or {}
print(
    "latency=%.1fs reasoning_tokens=%s completion=%s finish=%s content=%r"
    % (
        dt,
        (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        usage.get("completion_tokens"),
        data["choices"][0].get("finish_reason"),
        (data["choices"][0].get("message") or {}).get("content"),
    )
)
