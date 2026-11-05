"""SQLite 存储的读写（用临时库，不污染 data/tasks.db）。"""
from app import store


def _out(qid="Q001"):
    return {"qid": qid, "result": "通过", "trace": [{"step": 1, "tool": "x"}],
            "steps": 1, "cost_cny": 0.001}


def test_save_and_get_roundtrip(tmp_path):
    db = tmp_path / "t.db"
    tid = store.save(_out(), path=db)
    rec = store.get(tid, path=db)
    assert rec["qid"] == "Q001"
    assert rec["status"] == "done"
    assert rec["trace"] == [{"step": 1, "tool": "x"}]
    assert rec["cost_cny"] == 0.001


def test_get_missing_returns_none(tmp_path):
    db = tmp_path / "t.db"
    store.connect(db).close()
    assert store.get(999, path=db) is None


def test_multiple_rows(tmp_path):
    db = tmp_path / "t.db"
    a = store.save(_out("Q001"), path=db)
    b = store.save(_out("Q002"), path=db)
    assert b > a
    assert store.get(a, path=db)["qid"] == "Q001"
