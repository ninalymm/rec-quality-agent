"""构造混入降级样本的标注集。

问题：原始 200 条推荐的「理由」是强制引用生成的，几乎条条合格，
导致可解释性维度没有区分度（人 25/26 给 2 分，kappa 算不出来）。

做法：取 70 条原始 + 30 条**故意降级**，组成 100 条。
降级只改理由，不动标题/类目/日期，这样客观三维不变，
差异全部落在可解释性上——干净的对照实验。

用法：python -m scripts.make_mixed_set
输出：data/recs_mixed_v1.jsonl / judged_mixed_*.jsonl / labels_mixed.csv|md
"""
import csv
import json
import random
from concurrent.futures import ThreadPoolExecutor

from app import config
from eval.judge import judge

DATA = config.DATA_DIR
random.seed(20261103)

GENERIC = "根据您的历史行为为您推荐。"
FAKE_TITLES = ["《高效能人士的七个习惯》", "《人类简史》", "《深度工作》", "《原则》"]


def degrade_generic(recs):
    return [dict(r, reason=GENERIC) for r in recs]


def degrade_title_only(recs):
    """提标题但不说关系——按 rubric 应判 category，整组约 0 分。"""
    out = []
    for r in recs:
        out.append(dict(r, reason="你读过相关的内容，这篇讲 %s。" % r["title"]))
    return out


def degrade_half(recs):
    """保留 2 条真实理由，其余换成空泛说法——应约 1 分。"""
    out = []
    for i, r in enumerate(recs):
        out.append(dict(r, reason=r["reason"] if i < 2 else GENERIC))
    return out


def degrade_fabricated(recs):
    """引用历史里不存在的标题——应判 0，用于测 judge 会不会被骗。"""
    out = []
    for i, r in enumerate(recs):
        fake = FAKE_TITLES[i % len(FAKE_TITLES)]
        out.append(dict(r, reason="你最近在补%s，这篇正好接上，值得一看。" % fake))
    return out


def degrade_swapped(recs, other):
    """把别题的理由安过来——内容与理由不匹配。"""
    out = []
    for i, r in enumerate(recs):
        src = other[i % len(other)]
        out.append(dict(r, reason=src["reason"]))
    return out


def main():
    queries = {r["qid"]: r for r in csv.DictReader(
        open(DATA / "queries.csv", encoding="utf-8-sig"))}
    recs = [json.loads(l) for l in open(DATA / "recs_v1.jsonl", encoding="utf-8")]

    # 选 100 条：先保住边界题（可解释性非 null 的），再补常规
    usable = [r for r in recs if queries[r["qid"]]["history"].strip()]
    bound = [r for r in usable if r["note"] != "常规"]
    normal = [r for r in usable if r["note"] == "常规"]
    picked = bound + random.sample(normal, 100 - len(bound))
    picked = picked[:100]

    degrade_pool = picked[:30]
    keep = picked[30:]

    plan = [("generic", 6), ("title_only", 8), ("half", 6),
            ("fabricated", 6), ("swapped", 4)]
    idx = 0
    mixed = []
    for name, n in plan:
        for _ in range(n):
            src = degrade_pool[idx]
            idx += 1
            r = src["recommendations"]
            if name == "generic":
                new = degrade_generic(r)
            elif name == "title_only":
                new = degrade_title_only(r)
            elif name == "half":
                new = degrade_half(r)
            elif name == "fabricated":
                new = degrade_fabricated(r)
            else:
                other = random.choice(degrade_pool)["recommendations"]
                new = degrade_swapped(r, other)
            mixed.append({"qid": src["qid"], "note": src["note"], "variant": name,
                          "eval_date": src["eval_date"], "recommendations": new,
                          "expect": {"generic": "0 分", "title_only": "0 分",
                                     "half": "约 1 分", "fabricated": "0 分",
                                     "swapped": "0–1 分"}[name]})
    for src in keep:
        mixed.append({"qid": src["qid"], "note": src["note"], "variant": "original",
                      "eval_date": src["eval_date"],
                      "recommendations": src["recommendations"], "expect": "约 2 分"})

    random.shuffle(mixed)
    with open(DATA / "recs_mixed_v1.jsonl", "w", encoding="utf-8") as f:
        for m in mixed:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    # 双 judge
    for provider in ("deepseek", "qwen"):
        out_path = DATA / ("judged_mixed_%s.jsonl" % provider)

        def work(m, provider=provider):
            res = judge(queries[m["qid"]], m["recommendations"], provider=provider)
            return {"qid": m["qid"], "variant": m["variant"],
                    "dims": res["dims"], "summary": res["summary"],
                    "labels": res["explain_labels"], "cost_cny": res["cost_cny"]}

        with ThreadPoolExecutor(max_workers=6) as p:
            rows = list(p.map(work, mixed))
        with open(out_path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print("已判定 %s：%d 条" % (provider, len(rows)))

    # 标注表
    import csv as _csv
    cols = ["qid", "变体", "画像", "历史", "请求", "推荐1", "推荐2", "推荐3", "推荐4", "推荐5",
            "[代码]时效", "[代码]相关", "[代码]多样", "可解释性(0/1/2)", "备注"]
    judged = {json.loads(l)["qid"]: json.loads(l) for l in
              open(DATA / "judged_mixed_deepseek.jsonl", encoding="utf-8")}
    with open(DATA / "labels_mixed.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = _csv.writer(f)
        w.writerow(cols)
        for m in mixed:
            q, jd = queries[m["qid"]], judged[m["qid"]]["dims"]
            row = [m["qid"], m["variant"], q["user_profile"], q["history"], q["request"]]
            row += ["%s [%s] %s —— %s" % (r["title"], r["category"], r["published_at"], r["reason"])
                    for r in m["recommendations"]]
            row += [jd["timeliness"]["score"], jd["relevance"]["score"], jd["diversity"]["score"], "", ""]
            w.writerow(row)
    print("已生成 labels_mixed.csv（100 条，其中降级 30 条）")


if __name__ == "__main__":
    main()
