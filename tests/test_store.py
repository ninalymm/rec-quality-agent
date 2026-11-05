"""SQLite 存储的读写（用临时库，不污染 data/tasks.db）。"""
from app import store


def _out(qid="Q001"):
    return {"qid": qid, "result": "通过", "trace": [{"step": 1, "tool": "x"}],
            "steps": 1, "cost_cny": 0.001, "trace_id": "abc123"}


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


def test_trace_id_persisted(tmp_path):
    """trace_id 必须落库，否则拿到 task_id 也找不到对应日志。"""
    db = tmp_path / "t.db"
    tid = store.save(_out(), path=db)
    assert store.get(tid, path=db)["trace_id"] == "abc123"


def test_old_schema_migrated(tmp_path):
    """旧库没有 trace_id 列，connect 时应自动补上。"""
    import sqlite3
    db = tmp_path / "old.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, qid TEXT, status TEXT,"
                " result TEXT, trace TEXT, steps INTEGER, cost_cny REAL, created_at TEXT)")
    con.commit()
    con.close()
    con = store.connect(db)
    cols = {r[1] for r in con.execute("PRAGMA table_info(tasks)")}
    con.close()
    assert "trace_id" in cols


def test_default_path_uses_env(monkeypatch, tmp_path):
    """TASKS_DB 环境变量应覆盖默认库路径。"""
    monkeypatch.setenv("TASKS_DB", str(tmp_path / "container.db"))
    assert store.default_path() == tmp_path / "container.db"


def test_default_path_falls_back(monkeypatch):
    monkeypatch.delenv("TASKS_DB", raising=False)
    assert store.default_path().name == "tasks.db"
