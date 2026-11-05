"""结构化日志的格式契约。"""
import io
import json
import logging

from app.logging import (JsonFormatter, current_trace_id, log_step, log_task,
                         new_trace_id, trace_context)


def _capture():
    stream = io.StringIO()
    logger = logging.getLogger("test.recqa")
    logger.handlers.clear()
    h = logging.StreamHandler(stream)
    h.setFormatter(JsonFormatter())
    logger.addHandler(h)
    logger.setLevel("INFO")
    logger.propagate = False
    return logger, stream


def test_step_log_is_one_json_line():
    logger, stream = _capture()
    with trace_context("abc123"):
        log_step(logger, 1, "generate_recs", {"qid": "Q001"}, {"count": 5}, 1200)
    lines = [l for l in stream.getvalue().splitlines() if l.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    for key in ("ts", "level", "event", "trace_id", "step", "tool",
                "input", "output", "latency_ms", "ok"):
        assert key in rec, "缺少字段 %s" % key
    assert rec["event"] == "tool_step"
    assert rec["tool"] == "generate_recs"
    assert rec["trace_id"] == "abc123"        # 由上下文自动注入


def test_task_log_contains_status():
    logger, stream = _capture()
    with trace_context("abc123"):
        log_task(logger, "Q001", "done", 4, 0.006)
    rec = json.loads(stream.getvalue().strip())
    assert rec["event"] == "task_done"
    assert rec["status"] == "done"


def test_trace_id_is_short_and_unique():
    a, b = new_trace_id(), new_trace_id()
    assert len(a) == 12 and a != b


def test_no_trace_id_outside_context():
    """上下文之外不该凭空造一个 trace_id。"""
    logger, stream = _capture()
    log_step(logger, 1, "metrics_calc", {}, {}, 10)
    rec = json.loads(stream.getvalue().strip())
    assert "trace_id" not in rec


def test_context_is_restored_after_exit():
    assert current_trace_id() is None
    with trace_context() as tid:
        assert current_trace_id() == tid
    assert current_trace_id() is None


def test_nested_context_restores_outer():
    with trace_context("outer"):
        with trace_context("inner"):
            assert current_trace_id() == "inner"
        assert current_trace_id() == "outer"
