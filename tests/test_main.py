"""FastAPI 接口契约测试（stub 掉 run_task 与 store，不联网、不写库）。"""
from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


def test_health():
    assert client.get("/health").json() == {"ok": True}


def test_create_task_ok(monkeypatch):
    fake = {"qid": "Q001", "result": "通过", "trace": [], "steps": 4, "cost_cny": 0.001}
    monkeypatch.setattr(main, "run_task", lambda qid, provider=None: fake)
    monkeypatch.setattr(main.store, "save", lambda out: 7)

    r = client.post("/task", json={"qid": "Q001"})
    assert r.status_code == 200
    body = r.json()
    assert body["task_id"] == 7
    assert body["status"] == "done"
    assert body["steps"] == 4


def test_create_task_error_returns_500(monkeypatch):
    def boom(qid, provider=None):
        raise RuntimeError("模型超时")
    monkeypatch.setattr(main, "run_task", boom)

    r = client.post("/task", json={"qid": "Q001"})
    assert r.status_code == 500
    assert "RuntimeError" in r.json()["detail"]


def test_create_task_missing_qid():
    assert client.post("/task", json={}).status_code == 422


def test_get_task_ok(monkeypatch):
    monkeypatch.setattr(main.store, "get",
                        lambda tid: {"id": tid, "qid": "Q001", "trace": []})
    r = client.get("/task/3")
    assert r.status_code == 200
    assert r.json()["id"] == 3


def test_get_task_404(monkeypatch):
    monkeypatch.setattr(main.store, "get", lambda tid: None)
    assert client.get("/task/404").status_code == 404
