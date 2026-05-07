import json
import re
import time
import urllib.request
import urllib.error

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

from .config import PROVIDERS, PROVIDER_STATE


def _call_openai_compat(cfg: dict, messages: list, temperature: float) -> str:
    payload = {
        "model": cfg["model"],
        "stream": False,
        "temperature": temperature,
        "messages": messages,
    }
    headers = {"Authorization": f"Bearer {cfg['key']}"} if cfg["key"] else {}

    if _HAS_REQUESTS:
        for attempt in range(3):
            try:
                r = _requests.post(cfg["url"], headers=headers, json=payload, timeout=90)
                if r.status_code in (429, 503) or (r.status_code == 403 and attempt < 2):
                    wait = 2 ** attempt
                    print(f"    [限流] HTTP {r.status_code}，{wait}s 后重试...")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
            except _requests.HTTPError as e:
                raise RuntimeError(f"HTTP {e.response.status_code}: {e.response.text[:300]}") from e
        raise RuntimeError("重试次数耗尽")

    body = json.dumps(payload).encode()
    full_headers = {
        "Content-Type": "application/json",
        "User-Agent": "legal-expert-agent/1.0",
        **headers,
    }
    req = urllib.request.Request(cfg["url"], data=body, headers=full_headers, method="POST")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            body_err = e.read().decode()
            if e.code in (429, 503, 403) and attempt < 2:
                wait = 2 ** attempt
                print(f"    [限流] HTTP {e.code}，{wait}s 后重试...")
                time.sleep(wait)
                continue
            raise RuntimeError(f"HTTP {e.code}: {body_err[:300]}") from e
    raise RuntimeError("重试次数耗尽")


def _call_ollama(cfg: dict, messages: list, temperature: float) -> str:
    body = json.dumps({
        "model": cfg["model"],
        "stream": False,
        "options": {"temperature": temperature},
        "messages": messages,
    }).encode()
    req = urllib.request.Request(
        cfg["url"], data=body,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())["message"]["content"]


def chat(system: str, user: str, temperature: float = 0.1, provider: str = "") -> str:
    p = provider or PROVIDER_STATE["current"]
    cfg = PROVIDERS[p]
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]
    if p == "ollama":
        return _call_ollama(cfg, messages, temperature)
    return _call_openai_compat(cfg, messages, temperature)


def parse_json(raw: str, fallback):
    text = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
    for open_ch, close_ch in [('{', '}'), ('[', ']')]:
        s = text.find(open_ch)
        e = text.rfind(close_ch) + 1
        if 0 <= s < e:
            try:
                return json.loads(text[s:e])
            except json.JSONDecodeError:
                pass
    return fallback
