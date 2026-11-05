"""工具调度的依赖检查（离线，不调模型）。"""
from app.agent import TOOL_SPECS, TaskState, dispatch


def _stub(name, fn):
    old = TOOL_SPECS[name]["handler"]
    TOOL_SPECS[name]["handler"] = fn
    return old


def test_missing_prereq_returns_hint():
    state = TaskState("Q001")
    res = dispatch("metrics_calc", state, {})
    assert res["ok"] is False
    assert "recs" in res["error"]
    assert res["hint"] == "请先调用 generate_recs"


def test_unknown_tool():
    res = dispatch("nope", TaskState("Q001"), {})
    assert res["ok"] is False
    assert "未知工具" in res["error"]
    assert "generate_recs" in res["hint"]


def test_generate_has_no_prereq():
    state = TaskState("Q001")
    old = _stub("generate_recs", lambda s, a: {"count": 5})
    try:
        res = dispatch("generate_recs", state, {"qid": "Q001"})
        assert res["ok"] is True
        assert res["data"]["count"] == 5
    finally:
        _stub("generate_recs", old)


def test_handler_exception_is_caught():
    state = TaskState("Q001")
    state.recs = [{"title": "x"}]

    def boom(s, a):
        raise ValueError("bad input")

    old = _stub("metrics_calc", boom)
    try:
        res = dispatch("metrics_calc", state, {})
        assert res["ok"] is False
        assert "ValueError" in res["error"]
    finally:
        _stub("metrics_calc", old)


def test_provides_covers_requirements():
    """每个 requires 都能被某个工具的 provides 满足（依赖图没有断头）。"""
    provided = set()
    for spec in TOOL_SPECS.values():
        provided |= set(spec["provides"])
    for name, spec in TOOL_SPECS.items():
        for req in spec["requires"]:
            assert req in provided, "%s 需要 %s，但没有工具提供" % (name, req)


# ---------- 契约测试：handler 必须符合调度器的调用约定 ----------

import inspect


def test_every_handler_accepts_state_and_args():
    """调度器按 handler(state, args) 调用，签名必须能接受两个参数。

    这条测试就是 BUG-011 的防复发：当时三个 handler 只收一个参数，
    但单元测试用 stub 替换了它们，绕开了这个契约。
    """
    for name, spec in TOOL_SPECS.items():
        sig = inspect.signature(spec["handler"])
        try:
            sig.bind(TaskState("Q001"), {})
        except TypeError as exc:
            raise AssertionError(
                "工具 %s 的 handler 签名不兼容 handler(state, args): %s" % (name, exc))


def test_every_tool_has_description_and_schema():
    """模型靠 description 决定何时调用，缺了就会乱调。"""
    for name, spec in TOOL_SPECS.items():
        assert spec.get("description"), "%s 缺少 description" % name
        params = spec.get("parameters")
        assert isinstance(params, dict) and params.get("type") == "object", \
            "%s 的 parameters 不是合法 JSON Schema" % name


def test_dispatch_passes_args_through():
    """调度器必须原样把 args 传给 handler，而不是丢掉或改写。"""
    received = {}

    def capture(state, args):
        received.update(args)
        return {"ok": 1}

    old = _stub("generate_recs", capture)
    try:
        res = dispatch("generate_recs", TaskState("Q001"), {"qid": "Q999"})
        assert res["ok"] is True
        assert received == {"qid": "Q999"}
    finally:
        _stub("generate_recs", old)


# ---------- 评测已有推荐（不重新生成） ----------

from scripts.eval_recs import metrics_of


def test_metrics_of_basic():
    recs = [{"category": "技术", "reason": "12345"},
            {"category": "技术", "reason": "123"},
            {"category": "职场", "reason": "1234567"}]
    m = metrics_of(recs)
    assert m["count"] == 3
    assert m["types"] == 2
    assert m["type_dist"] == {"技术": 2, "职场": 1}
    assert m["avg_reason_len"] == 5.0


def test_metrics_of_empty():
    assert metrics_of([])["count"] == 0
