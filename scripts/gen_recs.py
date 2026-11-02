"""给 200 条 query 批量生成推荐（M2 的输入）。

并发调用，断点续跑，逐条记录成本。
用法：python -m scripts.gen_recs [--limit N] [--workers 6]
输出：data/recs_v1.jsonl
"""
import argparse
import csv
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from app import candidates, config
from app.recs import generate_recs

OUT = config.DATA_DIR / "recs_v1.jsonl"


def load_done():
    if not OUT.exists():
        return set()
    return {json.loads(l)["qid"] for l in open(OUT, encoding="utf-8") if l.strip()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(config.DATA_DIR / "queries.csv", encoding="utf-8-sig")))
    done = load_done()
    todo = [r for r in rows if r["qid"] not in done]
    if args.limit:
        todo = todo[: args.limit]

    pool = candidates.load_pool()
    eval_date = candidates.today()
    lock = threading.Lock()
    state = {"ok": 0, "fail": 0, "cost": 0.0}
    t0 = time.time()

    def work(r):
        out = generate_recs(r["user_profile"], r["history"], r["request"],
                            eval_date=eval_date, pool=pool)
        rec = {"qid": r["qid"], "note": r["note"], "eval_date": out["eval_date"],
               "recommendations": out["recommendations"],
               "cost_cny": out["cost_cny"], "model": out["model"],
               "tokens": out["tokens"]}
        with lock:
            with open(OUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            state["ok"] += 1
            state["cost"] += out["cost_cny"]

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

    print("\n完成 %d 条，失败 %d 条，耗时 %.1fs，总成本 ¥%.4f"
          % (state["ok"], state["fail"], time.time() - t0, state["cost"]))


if __name__ == "__main__":
    main()
