"""结构化日志的格式契约。"""
import io
import json
import logging

from app.logging import JsonFormatter, log_step, log_task, new_trace_id


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
    log_step(logger, "abc123", 1, "generate_recs", {"qid": "Q001"}, {"count": 5}, 1200)
    lines = [l for l in stream.getvalue().splitlines() if l.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    for key in ("ts", "level", "event", "trace_id", "step", "tool",
                "input", "output", "latency_ms", "ok"):
        assert key in rec, "缺少字段 %s" % key
    assert rec["event"] == "tool_step"
    assert rec["tool"] == "generate_recs"


def test_task_log_contains_status():
    logger, stream = _capture()
    log_task(logger, "abc123", "Q001", "done", 4, 0.006)
    rec = json.loads(stream.getvalue().strip())
    assert rec["event"] == "task_done"
    assert rec["status"] == "done"


def test_trace_id_is_short_and_unique():
    a, b = new_trace_id(), new_trace_id()
    assert len(a) == 12 and a != b
