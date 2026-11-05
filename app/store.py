"""M3：SQLite 持久化（任务 + 轨迹）。"""
import json
import sqlite3
import time
from pathlib import Path

from app import config

DB_PATH = config.ROOT / "data" / "tasks.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    qid TEXT NOT NULL,
    status TEXT NOT NULL,
    result TEXT,
    trace TEXT,
    steps INTEGER,
    cost_cny REAL,
    created_at TEXT
);
"""


def connect(path=None):
    con = sqlite3.connect(str(path or DB_PATH))
    con.executescript(SCHEMA)
    return con


def save(out, status="done", path=None):
    con = connect(path)
    cur = con.execute(
        "INSERT INTO tasks (qid, status, result, trace, steps, cost_cny, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (out["qid"], status, out["result"],
         json.dumps(out["trace"], ensure_ascii=False),
         out["steps"], out["cost_cny"],
         time.strftime("%Y-%m-%dT%H:%M:%S")))
    con.commit()
    tid = cur.lastrowid
    con.close()
    return tid


def get(tid, path=None):
    con = connect(path)
    row = con.execute(
        "SELECT id, qid, status, result, trace, steps, cost_cny, created_at"
        " FROM tasks WHERE id=?", (tid,)).fetchone()
    con.close()
    if not row:
        return None
    return {"id": row[0], "qid": row[1], "status": row[2], "result": row[3],
            "trace": json.loads(row[4] or "[]"), "steps": row[5],
            "cost_cny": row[6], "created_at": row[7]}
