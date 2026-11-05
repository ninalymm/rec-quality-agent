"""M4：超时、重试、降级。

取舍说明：
- 18.md 写「超时 3s」，那是针对本地快工具的。LLM 调用动辄 2–4s，
  3s 会把正常请求判死，所以按工具分级：本地工具 3s，LLM 工具 30s。
- 超时用线程 + future.result(timeout)，线程本身杀不掉，只保证调用方不再等；
  对 LLM 客户端来说，它自己的 timeout 会关掉连接。
"""
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from app.logging import get_logger

log = get_logger()

DEFAULT_TIMEOUTS = {"generate_recs": 30.0, "score_with_rubric": 30.0, "metrics_calc": 3.0}
DEFAULT_RETRIES = 2
BACKOFF = 0.5


class ToolTimeout(Exception):
    pass


def call_with_timeout(fn, timeout, *args, **kwargs):
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(fn, *args, **kwargs)
        try:
            return fut.result(timeout=timeout)
        except FutureTimeout:
            raise ToolTimeout("执行超过 %.1fs" % timeout)


def run_tool(name, fn, args=None, timeouts=None, retries=DEFAULT_RETRIES):
    """带超时与重试地执行一次工具。返回 (ok, data, error)。

    重试只针对异常，不针对超时——超时重试往往只是把等待翻倍。
    """
    timeouts = timeouts or DEFAULT_TIMEOUTS
    timeout = timeouts.get(name, 30.0)
    last = None
    for attempt in range(1, retries + 1):
        try:
            return True, call_with_timeout(fn, timeout, args), None
        except ToolTimeout as exc:
            last = "timeout: %s" % exc
            log.warning("tool_timeout", extra={"data": {"tool": name, "attempt": attempt}})
            break                      # 超时不重试
        except Exception as exc:
            last = "%s: %s" % (type(exc).__name__, str(exc)[:120])
            log.warning("tool_error", extra={"data": {"tool": name, "attempt": attempt,
                                                      "error": last}})
            if attempt < retries:
                time.sleep(BACKOFF * attempt)
    return False, None, last
