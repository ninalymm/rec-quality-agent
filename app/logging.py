"""M4：结构化日志——每个事件一行 JSON，便于 grep / 采集 / 对接 ELK。

为什么不用默认的 logging 文本格式：一行 JSON 可以直接被 jq 解析、
被日志系统按字段索引，而 "2026-11-05 14:23:01 INFO xxx" 这种格式只能人眼看。
"""
import contextlib
import contextvars
import json
import logging
import os
import sys
import time
import uuid

LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# trace_id 用 ContextVar 自动注入：调用方不必每次传，从结构上杜绝漏传
_trace_id: contextvars.ContextVar = contextvars.ContextVar("trace_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "data", {}) or {})
        # data 里没显式给 trace_id 时，从上下文自动补
        if not payload.get("trace_id"):
            tid = _trace_id.get()
            if tid:
                payload["trace_id"] = tid
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name="recqa"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(LEVEL)
        logger.propagate = False
    return logger


def new_trace_id():
    return uuid.uuid4().hex[:12]


def current_trace_id():
    return _trace_id.get()


@contextlib.contextmanager
def trace_context(trace_id=None):
    """在一个作用域内绑定 trace_id，退出时自动还原。

    注意：ContextVar 不会自动传播到新线程；本项目的日志都在主线程发出，
    所以够用。若将来在工具线程内打日志，需要 copy_context()。
    """
    token = _trace_id.set(trace_id or new_trace_id())
    try:
        yield _trace_id.get()
    finally:
        _trace_id.reset(token)


def log_step(logger, step, tool, args, result, latency_ms, ok=True, error=None):
    """记一步工具调用。trace_id 由上下文自动注入。

    字段与 18.md 对齐：trace_id, step, tool, input, output, latency。
    """
    logger.info("tool_step", extra={"data": {
        "step": step,
        "tool": tool,
        "input": args,
        "output": result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)[:200],
        "latency_ms": latency_ms,
        "ok": ok,
        "error": error,
    }})


def log_task(logger, qid, status, steps, cost_cny, error_reason=None):
    logger.info("task_done", extra={"data": {
        "qid": qid, "status": status,
        "steps": steps, "cost_cny": cost_cny, "error_reason": error_reason,
    }})
