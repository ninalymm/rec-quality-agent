"""judge 的契约测试与纯函数测试（不联网）。

重点：judge() 的返回结构是下游 agreement.py / REPORT 的输入，
一旦结构变了，应该在测试里崩，而不是跑完 200 条才崩。
"""
from datetime import date
from types import SimpleNamespace

import pytest

from eval import judge as J

EVAL = date(2026, 11, 5)


def _rec(days_ago, cat="技术", reason="你在看《X》，这篇讲 Y，同属一个问题"):
    return {"title": "t", "category": cat,
            "published_at": date.fromordinal(EVAL.toordinal() - days_ago).isoformat(),
            "reason": reason}


class TestObjectiveDims:
    def test_timeliness_median_bands(self):
        recs = [_rec(0), _rec(0), _rec(0), _rec(45), _rec(100)]
        assert J.score_timeliness(recs, EVAL)["score"] == 2      # 中位数 0 天

        recs = [_rec(45), _rec(45), _rec(45), _rec(0), _rec(100)]
        assert J.score_timeliness(recs, EVAL)["score"] == 1      # 中位数 45 天

        recs = [_rec(100), _rec(100), _rec(100), _rec(0), _rec(45)]
        assert J.score_timeliness(recs, EVAL)["score"] == 0      # 中位数 100 天

    def test_timeliness_needs_three_parseable(self):
        # 只有 2 条可解析 → null（不拿数据缺失扣分）
        recs = [_rec(10), _rec(10), dict(_rec(10), published_at="bad")]
        assert J.score_timeliness(recs, EVAL)["score"] is None

        # 3 条可解析（40/50/60 天），另 2 条无效 → 中位数 50 → 1 分
        recs = [_rec(40), _rec(50), _rec(60),
                dict(_rec(1), published_at="x"), dict(_rec(1), published_at="")]
        assert J.score_timeliness(recs, EVAL)["score"] == 1

    def test_relevance_null_without_interest(self):
        assert J.score_relevance([_rec(1)], "")["score"] is None

    def test_relevance_thresholds(self):
        recs = [_rec(1, "技术")] * 4 + [_rec(1, "娱乐")]
        assert J.score_relevance(recs, "技术;职场")["score"] == 2
        recs = [_rec(1, "技术")] * 2 + [_rec(1, "娱乐")] * 3
        assert J.score_relevance(recs, "技术")["score"] == 1
        recs = [_rec(1, "娱乐")] * 5
        assert J.score_relevance(recs, "技术")["score"] == 0

    def test_diversity_thresholds(self):
        assert J.score_diversity([_rec(1, c) for c in ["技术", "职场", "教育", "技术", "技术"]])["score"] == 2
        assert J.score_diversity([_rec(1, c) for c in ["技术", "职场", "技术", "技术", "技术"]])["score"] == 1
        assert J.score_diversity([_rec(1, "技术")] * 5)["score"] == 0


def _fake_client(monkeypatch, content):
    resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))
    client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=lambda **kw: resp)))
    cfg = {"model": "fake", "provider": "fake", "price_in": 1, "price_out": 1}
    monkeypatch.setattr(J, "client_for", lambda *a, **k: (client, cfg))


class TestExplainabilityContract:
    def test_returns_required_keys(self, monkeypatch):
        _fake_client(monkeypatch, '{"labels": ["specific","specific","category","vague","specific"], "evidence": "ok"}')
        out = J.judge_explainability([_rec(1)] * 5, "《X》")
        for key in ("score", "evidence", "labels", "specific_count", "cost_cny", "model"):
            assert key in out, "judge_explainability 缺少字段 %s" % key
        assert out["score"] == 1          # 3 条 specific → 1 分
        assert out["specific_count"] == 3

    def test_invalid_labels_normalized(self, monkeypatch):
        _fake_client(monkeypatch, '{"labels": ["具体","specific","??","vague","category"]}')
        out = J.judge_explainability([_rec(1)] * 5, "《X》")
        assert all(l in ("specific", "category", "vague") for l in out["labels"])

    def test_null_when_no_history(self, monkeypatch):
        out = J.judge_explainability([_rec(1)] * 5, "")
        assert out["score"] is None
        assert "不适用" in out["evidence"]


class TestJudgeOutputContract:
    def test_judge_returns_four_dims_and_summary(self, monkeypatch):
        monkeypatch.setattr(J, "judge_explainability",
                            lambda recs, hist, p=None, m=None: {"score": 2, "evidence": "stub",
                                                                "labels": [], "specific_count": 5,
                                                                "cost_cny": 0.0, "model": "stub"})
        q = {"qid": "Q001", "history": "《X》", "interest_categories": "技术"}
        out = J.judge(q, [_rec(1)] * 5, eval_date=EVAL)
        assert set(out["dims"]) == set(J.DIMS)
        for k in ("passed", "total", "grade", "partial"):
            assert k in out["summary"]


class TestAggregate:
    def test_all_one_passes(self):
        dims = {k: {"score": 1} for k in J.DIMS}
        assert J.aggregate(dims)["passed"] is True
        assert J.aggregate(dims)["total"] == 4

    def test_zero_fails(self):
        dims = {k: {"score": 2} for k in J.DIMS}
        dims["diversity"] = {"score": 0}
        assert J.aggregate(dims)["passed"] is False

    def test_null_excluded_from_pass_but_total_null(self):
        dims = {k: {"score": 2} for k in J.DIMS}
        dims["explainability"] = {"score": None}
        agg = J.aggregate(dims)
        assert agg["passed"] is True
        assert agg["total"] is None
        assert agg["partial"] is True
