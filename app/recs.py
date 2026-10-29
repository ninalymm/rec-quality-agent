"""业务层：一次 LLM 调用生成 N 条推荐。

M0 的最小闭环，也是 M3 里 generate_recs 工具的雏形。
"""
import json
import re

from openai import BadRequestError

from app import config
from app.llm import client_for, cost_cny
from app.prompts import build_recs_messages


def _loads(text):
    """解析模型返回：容忍 ```json 围栏和前后多余文字。"""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _extract_recs(data):
    """兼容几种常见返回形状：list / {"recommendations": [...]} / 其他首层列表。"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("recommendations"), list):
            return data["recommendations"]
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
    return []


def generate_recs(
    user_profile, history, request, provider=None, model=None,
    temperature=None, count=None,
):
    """一次 LLM 调用 → 推荐列表 + token 用量 + 成本。"""
    count = count or config.RECS_COUNT
    client, cfg = client_for(provider, model)
    kwargs = dict(
        model=cfg["model"],
        messages=build_recs_messages(user_profile, history, request, count),
        temperature=config.TEMPERATURE if temperature is None else temperature,
        max_tokens=config.MAX_TOKENS,
    )
    try:
        resp = client.chat.completions.create(
            response_format={"type": "json_object"}, **kwargs
        )
    except BadRequestError:
        # 有些本地/兼容端点不支持 response_format，退回普通模式，靠 _loads 兜住 JSON
        resp = client.chat.completions.create(**kwargs)

    raw = resp.choices[0].message.content or ""
    usage = resp.usage
    return {
        "recommendations": _extract_recs(_loads(raw)),
        "provider": cfg["provider"],
        "model": cfg["model"],
        "tokens": {
            "prompt": getattr(usage, "prompt_tokens", 0) or 0,
            "completion": getattr(usage, "completion_tokens", 0) or 0,
        },
        "cost_cny": round(cost_cny(cfg, usage), 6),
        "raw": raw,
    }
