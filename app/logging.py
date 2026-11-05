"""M4：结构化日志——每个事件一行 JSON，便于 grep / 采集 / 对接 ELK。

为什么不用默认的 logging 文本格式：一行 JSON 可以直接被 jq 解析、
被日志系统按字段索引，而 "2026-11-05 14:23:01 INFO xxx" 这种格式只能人眼看。
"""
import json
import logging
import os
import sys
import time
import uuid

LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "data", {}) or {})
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


def log_step(logger, trace_id, step, tool, args, result, latency_ms,
             ok=True, error=None):
    """记一步工具调用。字段与 18.md 要求对齐：trace_id, step, tool, input, output, latency。"""
    logger.info("tool_step", extra={"data": {
        "trace_id": trace_id,
        "step": step,
        "tool": tool,
        "input": args,
        "output": result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)[:200],
        "latency_ms": latency_ms,
        "ok": ok,
        "error": error,
    }})


def log_task(logger, trace_id, qid, status, steps, cost_cny, error_reason=None):
    logger.info("task_done", extra={"data": {
        "trace_id": trace_id, "qid": qid, "status": status,
        "steps": steps, "cost_cny": cost_cny, "error_reason": error_reason,
    }})
