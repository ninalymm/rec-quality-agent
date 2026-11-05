"""M3：FastAPI 入口。

POST /task        提交任务，返回 task_id
GET  /task/{id}   查询结果与 trace
GET  /health      健康检查
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import store
from app.agent import run_task

app = FastAPI(title="Rec-Quality Agent", version="0.1")


class TaskRequest(BaseModel):
    qid: str
    provider: str | None = None


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/task")
def create_task(req: TaskRequest):
    try:
        out = run_task(req.qid, provider=req.provider)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="%s: %s" % (type(exc).__name__, str(exc)[:120]))
    tid = store.save(out)
    return {"task_id": tid, "status": "done", "result": out["result"],
            "steps": out["steps"], "cost_cny": out["cost_cny"]}


@app.get("/task/{tid}")
def get_task(tid: int):
    rec = store.get(tid)
    if not rec:
        raise HTTPException(status_code=404, detail="task not found")
    return rec
