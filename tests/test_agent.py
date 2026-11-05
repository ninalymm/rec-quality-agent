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
