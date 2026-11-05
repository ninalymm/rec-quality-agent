"""超时、重试、降级的测试（不联网）。"""
import time

import pytest

from app.resilience import ToolTimeout, call_with_timeout, run_tool


def test_timeout_raises():
    with pytest.raises(ToolTimeout):
        call_with_timeout(lambda: time.sleep(1.5), 0.3)


def test_no_timeout_when_fast():
    assert call_with_timeout(lambda: 42, 1.0) == 42


def test_retry_then_success():
    calls = {"n": 0}

    def flaky(_):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return "ok"

    ok, data, err = run_tool("metrics_calc", flaky, {}, retries=3)
    assert ok is True and data == "ok" and err is None
    assert calls["n"] == 3


def test_retry_exhausted_returns_error():
    calls = {"n": 0}

    def always_fail(_):
        calls["n"] += 1
        raise ValueError("always")

    ok, data, err = run_tool("metrics_calc", always_fail, {}, retries=2)
    assert ok is False and data is None
    assert "ValueError" in err and "always" in err
    assert calls["n"] == 2          # 重试次数 = retries


def test_timeout_not_retried():
    """超时不重试——重试只会把等待翻倍。"""
    calls = {"n": 0}

    def slow(_):
        calls["n"] += 1
        time.sleep(0.6)
        return 1

    ok, data, err = run_tool("metrics_calc", slow, {},
                             timeouts={"metrics_calc": 0.2}, retries=3)
    assert ok is False and "timeout" in err
    assert calls["n"] == 1
