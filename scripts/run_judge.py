"""对已生成的推荐跑 judge（可指定 provider）。

用法：
    python -m scripts.run_judge --provider deepseek --limit 10
    python -m scripts.run_judge --provider qwen
输出：data/judged_<provider>.jsonl
"""
import argparse
import csv
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from app import config
from eval.judge import judge

DATA = config.DATA_DIR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="deepseek")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    out_path = DATA / ("judged_%s.jsonl" % args.provider)
    done = {json.loads(l)["qid"] for l in open(out_path, encoding="utf-8")} if out_path.exists() else set()

    queries = {r["qid"]: r for r in csv.DictReader(open(DATA / "queries.csv", encoding="utf-8-sig"))}
    recs = [json.loads(l) for l in open(DATA / "recs_v1.jsonl", encoding="utf-8")]
    todo = [r for r in recs if r["qid"] not in done]
    if args.limit:
        todo = todo[: args.limit]

    lock = threading.Lock()
    state = {"ok": 0, "fail": 0, "cost": 0.0}
    t0 = time.time()

    def work(r):
        q = queries[r["qid"]]
        res = judge(q, r["recommendations"], provider=args.provider,
                    eval_date=None)
        rec = {"qid": r["qid"], "note": r["note"], "provider": args.provider,
               "dims": res["dims"], "summary": res["summary"],
               "labels": res["explain_labels"], "cost_cny": res["cost_cny"]}
        with lock:
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            state["ok"] += 1
            state["cost"] += res["cost_cny"]

    with ThreadPoolExecutor(max_workers=args.workers) as p:
        futures = {p.submit(work, r): r["qid"] for r in todo}
        for n, fut in enumerate(as_completed(futures), 1):
            try:
                fut.result()
            except Exception as exc:
                with lock:
                    state["fail"] += 1
                print("  [fail] %s: %s" % (futures[fut], str(exc)[:90]))
            if n % 25 == 0:
                print("  进度 %d/%d，累计 ¥%.4f" % (n, len(todo), state["cost"]))

    print("\n完成 %d 条，失败 %d 条，耗时 %.1fs，成本 ¥%.4f"
          % (state["ok"], state["fail"], time.time() - t0, state["cost"]))


if __name__ == "__main__":
    main()
