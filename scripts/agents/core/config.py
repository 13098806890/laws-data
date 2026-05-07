from pathlib import Path

DB_PATH = Path("/Users/doxie/laws_data/law_content.db")

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
