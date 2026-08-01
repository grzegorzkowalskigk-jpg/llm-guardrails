"""EN: Shared Ollama chat client returning parsed JSON plus timing and token metrics.
PL: Wspolny klient czatu Ollamy zwracajacy sparsowany JSON oraz metryki czasu i tokenow.
"""
from __future__ import annotations

import json
import time
import urllib.request

OLLAMA = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen2.5:3b"


def chat_json(prompt: str, model: str = DEFAULT_MODEL, timeout: int = 600) -> tuple[dict, dict]:
    """EN: Sends a prompt and returns (parsed JSON, metrics).
    PL: Wysyla prompt i zwraca (sparsowany JSON, metryki).
    """
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.load(r)
    metrics = {
        "seconds": round(time.perf_counter() - t0, 2),
        "tokens_in": out.get("prompt_eval_count", 0),
        "tokens_out": out.get("eval_count", 0),
    }
    try:
        parsed = json.loads(out["message"]["content"])
    except json.JSONDecodeError:
        parsed = {"_parse_error": out["message"]["content"][:400]}
    return parsed, metrics
