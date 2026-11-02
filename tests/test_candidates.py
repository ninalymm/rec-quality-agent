"""候选池与校验的离线单测。"""
from datetime import date

from app import candidates as C
from app import validate as V

EVAL = date(2026, 11, 2)
POOL = [
    {"id": "C1", "title": "标题一", "category": "技术", "summary": "s", "age_days": "5"},
    {"id": "C2", "title": "标题二", "category": "职场", "summary": "s", "age_days": "40"},
    {"id": "C3", "title": "标题三", "category": "教育", "summary": "s", "age_days": "100"},
]


def test_published_at_from_age():
    assert C.published_at(5, EVAL) == "2026-10-28"
    assert C.published_at(40, EVAL) == "2026-09-23"


def test_enrich_fills_fields():
    out = C.enrich([{"id": "C1", "reason": "因为看过《标题一》"}], POOL, EVAL)
    assert out[0]["title"] == "标题一"
    assert out[0]["category"] == "技术"
    assert out[0]["published_at"] == "2026-10-28"


def test_enrich_drops_unknown_id():
    assert C.enrich([{"id": "C9", "reason": "x"}], POOL, EVAL) == []


def test_cited_titles():
    assert V.cited_titles("看过《Go 内存模型》和《跑步》") == ["Go 内存模型", "跑步"]


def test_cites_any():
    assert V.cites_any("你在看《Go 内存模型》", ["Go 内存模型"])
    assert not V.cites_any("你在关注技术领域", ["Go 内存模型"])


def _recs():
    return [
        {"id": "C1", "title": "标题一", "category": "技术", "published_at": "2026-10-28", "reason": "你在看《标题一》，同源"},
        {"id": "C2", "title": "标题二", "category": "职场", "published_at": "2026-09-23", "reason": "你在看《标题一》，换个角度"},
        {"id": "C3", "title": "标题三", "category": "教育", "published_at": "2026-07-25", "reason": "延续《标题一》的学习路径"},
        {"id": "C1", "title": "标题一", "category": "技术", "published_at": "2026-10-28", "reason": "重复条目"},
        {"id": "C2", "title": "标题二", "category": "职场", "published_at": "2026-09-23", "reason": "重复条目"},
    ]


def test_check_flags_duplicate_ids():
    rep = V.check(_recs(), POOL, EVAL, count=5, history="《标题一》")
    assert not rep["ok"]
    assert any("重复" in e for e in rep["errors"])


def test_check_flags_short_reason():
    recs = _recs()[:3] + [
        {"id": "C1", "title": "t", "category": "技术", "published_at": "2026-10-28", "reason": "短"},
        {"id": "C2", "title": "t", "category": "职场", "published_at": "2026-09-23", "reason": ""},
    ]
    rep = V.check(recs, POOL, EVAL, history="")
    assert any("理由过短" in e for e in rep["errors"])


def test_check_flags_future_date():
    recs = list(_recs()[:5])
    recs[0] = dict(recs[0], published_at="2027-01-01")
    rep = V.check(recs, POOL, EVAL)
    assert any("未来" in e for e in rep["errors"])


def test_check_stats():
    recs = _recs()[:3]
    rep = V.check(recs, POOL, EVAL, count=3, history="《标题一》")
    assert rep["stats"]["types"] == 3
    assert rep["stats"]["cites"] == 3
