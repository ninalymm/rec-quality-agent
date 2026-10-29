"""LLM 客户端工厂：一套代码切换 DeepSeek / Qwen / 本地 Ollama。

三家都兼容 OpenAI 协议，差异只有三个值：base_url、model、API key 的环境变量名。
价格写在 PROVIDERS 里，供成本估算用；按官网标价填写，变动时只改这里。
"""
import os

from openai import OpenAI

from app import config


class MissingKeyError(RuntimeError):
    """没有 key 时给出可执行的提示，而不是让 SDK 抛一句难懂的 401。"""


PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "key_env": "DEEPSEEK_API_KEY",
        "price_in": 2.0,   # ¥ / 百万 input token
        "price_out": 8.0,  # ¥ / 百万 output token
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "key_env": "DASHSCOPE_API_KEY",
        "price_in": 0.8,
        "price_out": 2.0,
    },
    # 本地兜底：ollama serve 之后即可用，不花钱、不需要真 key
    "ollama": {
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "model": os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
        "key_env": "OLLAMA_API_KEY",
        "default_key": "ollama",  # ollama 不校验 key，占位即可
        "price_in": 0.0,
        "price_out": 0.0,
    },
}


def resolve(provider=None, model=None):
    """把 provider 名字解析成完整配置；缺 key 直接抛 MissingKeyError。"""
    name = provider or config.DEFAULT_PROVIDER
    if name not in PROVIDERS:
        raise ValueError(
            "未知 provider %r，可选：%s" % (name, ", ".join(sorted(PROVIDERS)))
        )
    cfg = dict(PROVIDERS[name])
    key = os.getenv(cfg["key_env"], "").strip() or cfg.get("default_key", "")
    if not key:
        raise MissingKeyError(
            "缺少 %s。\n"
            "  cp .env.example .env   # 然后填入你的 key\n"
            "（.env 已在 .gitignore 里，不会被提交）" % cfg["key_env"]
        )
    cfg["api_key"] = key
    cfg["provider"] = name
    cfg["model"] = model or cfg["model"]
    return cfg


def client_for(provider=None, model=None, timeout=None):
    """返回 (OpenAI client, cfg)。timeout 必须设，否则网络抖动会挂住。"""
    cfg = resolve(provider, model)
    client = OpenAI(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        timeout=timeout or config.REQUEST_TIMEOUT,
    )
    return client, cfg


def cost_cny(cfg, usage):
    """按官网标价估算一次调用的成本（元）。usage 可能为 None。"""
    if usage is None:
        return 0.0
    prompt = getattr(usage, "prompt_tokens", 0) or 0
    completion = getattr(usage, "completion_tokens", 0) or 0
    return (prompt * cfg["price_in"] + completion * cfg["price_out"]) / 1e6
