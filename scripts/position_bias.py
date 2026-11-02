"""位置偏差实验：把 5 条推荐顺序反过来重判一次，看分数变不变。

只有可解释性维度可能变化——另外三维是集合计算，与顺序无关。
用法：python -m scripts.position_bias --n 50 [--provider deepseek|qwen]
"""
import argparse
import json

from app import config
from eval.judge import judge

import csv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--provider", default="deepseek")
    args = ap.parse_args()

    queries = {r["qid"]: r for r in csv.DictReader(
        open(config.DATA_DIR / "queries.csv", encoding="utf-8-sig"))}
    recs = [json.loads(l) for l in open(config.DATA_DIR / "recs_v1.jsonl", encoding="utf-8")]
    base = {json.loads(l)["qid"]: json.loads(l) for l in
            open(config.DATA_DIR / ("judged_%s.jsonl" % args.provider), encoding="utf-8")}

    sample = recs[: args.n]
    changed = 0
    deltas = []
    for r in sample:
        q = queries[r["qid"]]
        flipped = list(reversed(r["recommendations"]))
        res = judge(q, flipped, provider=args.provider)
        old = base[r["qid"]]["dims"]["explainability"]["score"]
        new = res["dims"]["explainability"]["score"]
        if old != new:
            changed += 1
            deltas.append(new - old)

    n = len(sample)
    print("provider=%s  样本=%d" % (args.provider, n))
    print("可解释性分数变化：%d 条（%.1f%%）" % (changed, changed / n * 100))
    if deltas:
        print("变化方向：变高 %d 条 / 变低 %d 条" % (
            sum(1 for d in deltas if d > 0), sum(1 for d in deltas if d < 0)))
        print("平均变化：%+.2f" % (sum(deltas) / len(deltas)))


if __name__ == "__main__":
    main()
