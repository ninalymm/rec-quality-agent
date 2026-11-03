"""生成人工标注表（盲标：不含 judge 的可解释性分数）。

按 F8 的结论：客观三维由代码预填（只读参考），人只标「可解释性」。
用法：
    python -m scripts.make_label_sheet --tag main --n 100
输出：data/labels_<tag>.csv / .md
"""
import argparse
import csv
import json

from app import config

COLS = ["qid", "画像", "历史", "兴趣类目", "请求",
        "推荐1", "推荐2", "推荐3", "推荐4", "推荐5",
        "[代码]时效", "[代码]相关", "[代码]多样", "可解释性(0/1/2)", "备注"]


def fmt(r):
    return "%s [%s] %s —— %s" % (r["title"], r["category"], r["published_at"], r["reason"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--tag", default="main")
    args = ap.parse_args()

    queries = {r["qid"]: r for r in csv.DictReader(
        open(config.DATA_DIR / "queries.csv", encoding="utf-8-sig"))}
    recs = {json.loads(l)["qid"]: json.loads(l) for l in
            open(config.DATA_DIR / "recs_v1.jsonl", encoding="utf-8")}
    judged = {json.loads(l)["qid"]: json.loads(l) for l in
              open(config.DATA_DIR / "judged_deepseek.jsonl", encoding="utf-8")}

    # 边界全收（可解释性为 null 的除外），常规按顺序补足
    pool = [q for q in queries if judged[q]["dims"]["explainability"]["score"] is not None]
    bound = [q for q in pool if queries[q]["note"] != "常规"]
    normal = [q for q in pool if queries[q]["note"] == "常规"]
    picked = bound + normal[: max(0, args.n - len(bound))]
    picked = picked[: args.n]

    path_csv = config.DATA_DIR / ("labels_%s.csv" % args.tag)
    with open(path_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        for q in picked:
            qr, rr, jd = queries[q], recs[q]["recommendations"], judged[q]["dims"]
            row = [q, qr["user_profile"], qr["history"] or "（无）",
                   qr["interest_categories"] or "（无）", qr["request"]]
            row += [fmt(r) for r in rr] + [""] * (5 - len(rr))
            row += [jd["timeliness"]["score"], jd["relevance"]["score"],
                    jd["diversity"]["score"], "", ""]
            w.writerow(row)

    md = ["# 人工标注表（%s，%d 条）" % (args.tag, len(picked)), "",
          "> **只标「可解释性」一列**。前三列标了 `[代码]`，由代码计算，仅供参考，不用填。",
          "> 量表：0 / 1 / 2；无历史时该维度不适用，填 null（本轮已排除这类样本）。", "",
          "## 判定标准", "",
          "| 分 | 条件 |",
          "|---|---|",
          "| 2 | ≥4 条理由**既提到**历史里的具体标题，**又说明了**这篇与该标题是什么关系 |",
          "| 1 | 2–3 条做到 |",
          "| 0 | ≤1 条做到 |",
          "",
          "**不算「说明关系」的写法**（判 category，不计入具体条数）：",
          "",
          "- 「你在看《摄影入门》，咖啡入门同样属于可上手的生活技能型入门内容」→ 只是同属一类",
          "- 「和你读过的《服务雪崩与熔断》一样讲的是识别风险信号」→ 类比跨到不同领域",
          "- 「你读过《容器镜像瘦身》，对 K8s 已有基础」→ 没说清这两篇的具体关系",
          "",
          "**判定口诀**：把推荐内容换掉，这个理由还成立吗？换掉就说不通的才算具体。", ""]

    for q in picked[:30]:
        qr, rr, jd = queries[q], recs[q]["recommendations"], judged[q]["dims"]
        md += ["---", "", "## %s　`%s`" % (q, qr["note"]), "",
               "- 画像：%s" % qr["user_profile"],
               "- 历史：%s" % (qr["history"] or "（无）"),
               "- 请求：%s" % qr["request"],
               "- 代码算的：时效 %s / 相关 %s / 多样 %s" % (
                   jd["timeliness"]["score"], jd["relevance"]["score"], jd["diversity"]["score"]), ""]
        for i, r in enumerate(rr, 1):
            md.append("%d. **%s**  \n   %s" % (i, r["title"], r["reason"]))
        md += ["", "**可解释性**：___　备注：______", ""]
    (config.DATA_DIR / ("labels_%s.md" % args.tag)).write_text("\n".join(md), encoding="utf-8")

    print("已生成 %d 条：%s / labels_%s.md" % (len(picked), path_csv.name, args.tag))
    print("其中边界 %d 条，常规 %d 条" % (len(bound), len(picked) - len(bound)))


if __name__ == "__main__":
    main()
