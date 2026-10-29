"""解析层与 prompt 层的离线单测：不需要 key、不联网。"""
import json

import pytest

from app.prompts import build_recs_messages
from app.recs import _extract_recs, _loads


class TestLoads:
    def test_plain_json(self):
        assert _loads('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        assert _loads('```json\n{"recommendations": []}\n```') == {"recommendations": []}

    def test_leading_chatter(self):
        text = '好的，结果如下：{"recommendations": [{"title": "x"}]} 以上。'
        assert _loads(text)["recommendations"][0]["title"] == "x"

    def test_garbage_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _loads("完全不是 JSON")


class TestExtract:
    def test_from_dict(self):
        data = {"recommendations": [{"title": "a"}, {"title": "b"}]}
        assert len(_extract_recs(data)) == 2

    def test_from_list(self):
        assert len(_extract_recs([{"title": "a"}])) == 1

    def test_unknown_shape(self):
        assert _extract_recs({"foo": "bar"}) == []

    def test_falls_back_to_first_list(self):
        data = {"items": [{"title": "a"}]}
        assert _extract_recs(data)[0]["title"] == "a"


class TestMessages:
    def test_contains_profile_and_history(self):
        msgs = build_recs_messages("28 岁后端", "看过 Go", "推荐 5 条", count=5)
        assert msgs[0]["role"] == "system"
        assert "28 岁后端" in msgs[1]["content"]
        assert "看过 Go" in msgs[1]["content"]

    def test_count_goes_into_system_prompt(self):
        msgs = build_recs_messages("p", "h", "r", count=3)
        assert "3" in msgs[0]["content"]
