"""provider 解析与成本计算的离线单测。"""
import pytest

from app.llm import MissingKeyError, PROVIDERS, cost_cny, resolve


class Usage:
    prompt_tokens = 1000
    completion_tokens = 500


def test_cost_cny_math():
    # deepseek: 2 元/M input, 8 元/M output
    assert cost_cny(PROVIDERS["deepseek"], Usage()) == pytest.approx(0.002 + 0.004)


def test_cost_cny_none_usage():
    assert cost_cny(PROVIDERS["deepseek"], None) == 0.0


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(MissingKeyError):
        resolve("deepseek")


def test_key_from_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    cfg = resolve("deepseek")
    assert cfg["api_key"] == "sk-test"
    assert cfg["model"] == "deepseek-chat"


def test_model_override(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    assert resolve("qwen", model="qwen-max")["model"] == "qwen-max"


def test_ollama_needs_no_real_key(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    assert resolve("ollama")["api_key"] == "ollama"


def test_unknown_provider():
    with pytest.raises(ValueError):
        resolve("nope")
