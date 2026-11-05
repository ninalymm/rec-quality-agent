"""跑一个 Agent 任务并打印 trace（M3 的验收脚本）。

用法：
    python -m scripts.run_task --qid Q001
    python -m scripts.run_task --qid Q001 Q002 Q003
"""
import argparse

from app import store
from app.agent import run_task


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qid", nargs="+", default=["Q001"])
    ap.add_argument("--provider", default=None)
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()

    for qid in args.qid:
        print("=" * 66)
        print("任务：%s" % qid)
        out = run_task(qid, provider=args.provider)
        print("-" * 66)
        print("%-4s %-18s %-9s %s" % ("步", "工具", "耗时", "结果摘要"))
        for t in out["trace"]:
            print("%-4d %-18s %-9s %s" % (t["step"], t["tool"],
                                          "%dms" % t["latency_ms"], t["result"][:60]))
        print("-" * 66)
        print("结论：%s" % out["result"])
        print("步数 %d，成本 ¥%.6f" % (out["steps"], out["cost_cny"]))
        if not args.no_save:
            tid = store.save(out)
            print("已存库 id=%d" % tid)
        print()


if __name__ == "__main__":
    main()
