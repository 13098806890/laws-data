import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DB_PATH = Path(os.environ.get("LAWS_DB_PATH", BASE_DIR / "law_content.db"))

PROVIDERS = {
    "groq": {
        "url":   "https://api.groq.com/openai/v1/chat/completions",
        "key":   "",   # 填入 Groq API Key（https://console.groq.com/keys）
        "model": "llama-3.3-70b-versatile",
    },
    "deepseek": {
        "url":   "https://api.deepseek.com/chat/completions",
        "key":   "",   # 填入 DeepSeek API Key（https://platform.deepseek.com/api_keys）
        "model": "deepseek-chat",
    },
    "ollama": {
        "url":   "http://localhost:11434/api/chat",
        "key":   "",
        "model": "qwen2.5:3b",
    },
}

DEFAULT_PROVIDER = "deepseek"

PROVIDER_STATE: dict = {"current": DEFAULT_PROVIDER}
