"""agent 主循环的编排逻辑（用假 client，不联网）。"""
from types import SimpleNamespace

from app import agent as A


class FakeMsg:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, **kw):
        return {"role": "assistant", "content": self.content}


def _resp(msg):
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                           usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


def _call(name, args="{}", cid="c1"):
    return SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments=args))


def _fake_client(monkeypatch, responses):
    queue = list(responses)

    def create(**kw):
        return queue.pop(0)

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    cfg = {"model": "fake", "provider": "fake", "price_in": 0, "price_out": 0}
    monkeypatch.setattr(A, "client_for", lambda *a, **k: (client, cfg))


def _stub_tools(monkeypatch):
    """stub 必须履行 provides 契约：返回数据的同时真的写进 state。

    只返回 dict 不写 state，下游的前置检查会继续报「缺少前置数据」——
    这是 stub 测试最常见的失真方式。
    """
    def gen(s, a):
        s.recs = [{"category": "技术", "reason": "x"}]
        return {"count": 1}

    def metrics(s, a):
        s.metrics = {"types": 1}
        return s.metrics

    def score(s, a):
        s.judgement = {"summary": {"total": 6, "grade": "合格", "passed": True},
                       "dims": {"timeliness": 2}}
        return {"dims": {"timeliness": 2}}

    monkeypatch.setitem(A.TOOL_SPECS["generate_recs"], "handler", gen)
    monkeypatch.setitem(A.TOOL_SPECS["metrics_calc"], "handler", metrics)
    monkeypatch.setitem(A.TOOL_SPECS["score_with_rubric"], "handler", score)


def test_normal_path_three_tools_then_final(monkeypatch):
    _stub_tools(monkeypatch)
    _fake_client(monkeypatch, [
        _resp(FakeMsg(tool_calls=[_call("generate_recs", '{"qid": "Q001"}')])),
        _resp(FakeMsg(tool_calls=[_call("metrics_calc")])),
        _resp(FakeMsg(tool_calls=[_call("score_with_rubric")])),
        _resp(FakeMsg(content="完成，通过")),
    ])
    out = A.run_task("Q001")
    assert out["result"] == "完成，通过"
    assert [t["tool"] for t in out["trace"]] == [
        "generate_recs", "metrics_calc", "score_with_rubric", "(final)"]
    assert out["tool_errors"] == 0
    assert out["trace_id"]


def test_precondition_error_recorded_and_model_can_recover(monkeypatch):
    _stub_tools(monkeypatch)
    _fake_client(monkeypatch, [
        _resp(FakeMsg(tool_calls=[_call("metrics_calc")])),          # 顺序错
        _resp(FakeMsg(tool_calls=[_call("generate_recs")])),
        _resp(FakeMsg(content="补做后完成")),
    ])
    out = A.run_task("Q001")
    assert out["trace"][0]["ok"] is False
    assert "缺少前置数据" in out["trace"][0]["error"]
    assert out["trace"][1]["ok"] is True
    assert out["status"] == "partial"      # 有推荐但没判定


def test_max_steps_exhausted(monkeypatch):
    _stub_tools(monkeypatch)
    looping = [_resp(FakeMsg(tool_calls=[_call("generate_recs")])) for _ in range(4)]
    _fake_client(monkeypatch, looping)
    out = A.run_task("Q001", max_steps=3)
    assert len(out["trace"]) == 3
    assert out["result"] == ""             # 没有最终答案，也没有判定


def test_fallback_answer_from_judgement(monkeypatch):
    _stub_tools(monkeypatch)
    monkeypatch.setitem(A.TOOL_SPECS["score_with_rubric"], "handler",
                        lambda s, a: _set_judgement(s))

    def _set_judgement(s):
        s.judgement = {"summary": {"total": 6, "grade": "合格", "passed": True}}
        return {}

    _fake_client(monkeypatch, [
        _resp(FakeMsg(tool_calls=[_call("generate_recs")])),
        _resp(FakeMsg(tool_calls=[_call("score_with_rubric")])),
    ])
    out = A.run_task("Q001", max_steps=2)
    assert "总分 6" in out["result"]
