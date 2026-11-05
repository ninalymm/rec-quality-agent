"""查看任务数据库，不用装任何 GUI 工具。

用法：
    python -m scripts.inspect_db                # 最近 10 条任务
    python -m scripts.inspect_db --limit 3
    python -m scripts.inspect_db --trace 9      # 看某个任务的完整轨迹
"""
import argparse
import json

from app import store


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--trace", type=int, default=None, help="查看指定 task id 的轨迹")
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    path = args.db or store.default_path()
    print("数据库: %s\n" % path)
    con = store.connect(path)

    if args.trace is not None:
        rec = store.get(args.trace, path=path)
        if not rec:
            print("没有 id=%d 的任务" % args.trace)
            return
        print("任务 %d | qid=%s | status=%s | steps=%d | ¥%.5f | %s"
              % (rec["id"], rec["qid"], rec["status"], rec["steps"],
                 rec["cost_cny"], rec["trace_id"]))
        print("结论: %s\n" % rec["result"])
        print("%-4s %-18s %-8s %s" % ("步", "工具", "耗时", "结果"))
        print("-" * 78)
        for t in rec["trace"]:
            print("%-4d %-18s %-8s %s" % (t["step"], t["tool"],
                                          "%dms" % t["latency_ms"], t["result"][:46]))
        return

    rows = con.execute(
        "SELECT id, qid, status, steps, cost_cny, trace_id, created_at"
        " FROM tasks ORDER BY id DESC LIMIT ?", (args.limit,)).fetchall()
    if not rows:
        print("还没有任务记录")
        return
    print("%-4s %-6s %-8s %-6s %-9s %-14s %s" % ("id", "qid", "status", "steps", "成本", "trace_id", "时间"))
    print("-" * 78)
    for r in rows:
        print("%-4d %-6s %-8s %-6d ¥%-8.5f %-14s %s"
              % (r[0], r[1], r[2], r[3], r[4], r[5] or "-", r[6]))
    total = con.execute("SELECT COUNT(*), ROUND(SUM(cost_cny),4) FROM tasks").fetchone()
    print("\n共 %d 条，累计成本 ¥%s" % (total[0], total[1]))


if __name__ == "__main__":
    main()
