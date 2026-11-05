"""评测**已经生成好**的推荐，不重新生成。

用途：生产系统产出的推荐、人工构造的对照集、或者历史落盘的推荐，都可以直接喂进来打分。

输入：JSONL，每行至少含 qid 与 recommendations
    {"qid": "Q001", "recommendations": [
        {"title": "...", "category": "技术", "published_at": "2026-10-20", "reason": "..."}, ...]}

用法：
    python -m scripts.eval_recs --input data/recs_v1.jsonl --limit 5
    python -m scripts.eval_recs --input my_recs.jsonl --provider qwen

输出：终端汇总 + data/evaluated_<input名>.jsonl
"""
import argparse
import csv
import json
import pathlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from app import config
from eval.judge import judge

DATA = config.DATA_DIR


def load_queries():
    return {r["qid"]: r for r in csv.DictReader(
        open(DATA / "queries.csv", encoding="utf-8-sig"))}


def metrics_of(recs):
    types = {}
    for r in recs:
        types[r.get("category", "?")] = types.get(r.get("category", "?"), 0) + 1
    return {
        "count": len(recs),
        "types": len(types),
        "type_dist": types,
        "avg_reason_len": round(sum(len(r.get("reason") or "") for r in recs) / len(recs), 1)
        if recs else 0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="JSONL 文件，含 qid 与 recommendations")
    ap.add_argument("--provider", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    src = pathlib.Path(args.input)
    if not src.exists():          # 允许只写文件名（默认在 data/ 下找）
        src = DATA / args.input
    rows = [json.loads(l) for l in open(src, encoding="utf-8") if l.strip()]
    if args.limit:
        rows = rows[: args.limit]
    queries = load_queries()

    out_name = "evaluated_%s.jsonl" % src.stem
    out_path = DATA / out_name

    lock = threading.Lock()
    state = {"ok": 0, "fail": 0, "cost": 0.0}
    results = []
    t0 = time.time()

    def work(row):
        qid = row.get("qid")
        recs = row.get("recommendations") or []
        q = queries.get(qid)
        if q is None:
            raise KeyError("queries.csv 里没有 %s" % qid)
        if len(recs) != 5:
            raise ValueError("%s 的推荐条数是 %d，不是 5" % (qid, len(recs)))
        res = judge(q, recs, provider=args.provider)
        rec = {"qid": qid, "provider": args.provider or "default",
               "metrics": metrics_of(recs),
               "dims": res["dims"], "summary": res["summary"],
               "cost_cny": res["cost_cny"]}
        with lock:
            results.append(rec)
            state["ok"] += 1
            state["cost"] += res["cost_cny"]
        return rec

    with ThreadPoolExecutor(max_workers=args.workers) as p:
        futures = {p.submit(work, r): r.get("qid") for r in rows}
        for n, fut in enumerate(as_completed(futures), 1):
            try:
                fut.result()
            except Exception as exc:
                with lock:
                    state["fail"] += 1
                print("  [fail] %s: %s" % (futures[fut], str(exc)[:90]))
            if n % 25 == 0:
                print("  进度 %d/%d" % (n, len(rows)))

    results.sort(key=lambda r: r["qid"])
    with open(out_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    passed = sum(1 for r in results if r["summary"]["passed"])
    totals = [r["summary"]["total"] for r in results if r["summary"]["total"] is not None]
    print("\n评测 %d 条（失败 %d），耗时 %.1fs，成本 ¥%.4f"
          % (state["ok"], state["fail"], time.time() - t0, state["cost"]))
    if results:
        print("通过率 %.1f%%（%d/%d）｜平均总分 %.2f｜结果写入 %s"
              % (passed / len(results) * 100, passed, len(results),
                 sum(totals) / len(totals) if totals else 0, out_name))


if __name__ == "__main__":
    main()
