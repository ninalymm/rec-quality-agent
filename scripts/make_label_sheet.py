"""生成人工标注表（盲标：不含任何 judge 分数）。

用法：
    python -m scripts.make_label_sheet --n 10 --tag pilot
输出：
    data/labels_<tag>.csv   给 Excel 填
    data/labels_<tag>.md    方便通读
"""
import argparse
import csv
import json

from app import config

COLS = ["qid", "画像", "历史", "兴趣类目", "请求",
        "推荐1", "推荐2", "推荐3", "推荐4", "推荐5",
        "时效性", "相关性", "多样性", "可解释性", "备注"]


def fmt(r):
    return "%s [%s] %s —— %s" % (r["title"], r["category"], r["published_at"], r["reason"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--tag", default="pilot")
    args = ap.parse_args()

    queries = {r["qid"]: r for r in csv.DictReader(
        open(config.DATA_DIR / "queries.csv", encoding="utf-8-sig"))}
    recs = {json.loads(l)["qid"]: json.loads(l) for l in
            open(config.DATA_DIR / "recs_v1.jsonl", encoding="utf-8")}

    # 分层抽样：常规 7 + 边界 3，边界优先覆盖不同类型
    normal = [q for q in queries if queries[q]["note"] == "常规"]
    bound = [q for q in queries if queries[q]["note"] != "常规"]
    seen = set()
    picked = []
    for q in bound:
        n = queries[q]["note"]
        if n not in seen:
            seen.add(n)
            picked.append(q)
        if len(picked) >= 3:
            break
    for q in normal:
        if len(picked) >= args.n:
            break
        picked.append(q)

    out_csv = config.DATA_DIR / ("labels_%s.csv" % args.tag)
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        for q in picked:
            qr = queries[q]
            rr = recs.get(q, {}).get("recommendations", [])
            row = [q, qr["user_profile"], qr["history"] or "（无）",
                   qr["interest_categories"] or "（无）", qr["request"]]
            row += [fmt(r) for r in rr] + [""] * (5 - len(rr))
            row += ["", "", "", "", ""]
            w.writerow(row)

    md = ["# 人工标注表（%s）" % args.tag, "",
          "> **盲标**：表里不含 judge 的任何分数。",
          "> 量表：每维 0/1/2，无数据填 null；四维均 ≥1 才算通过。", ""]
    for q in picked:
        qr = queries[q]
        rr = recs.get(q, {}).get("recommendations", [])
        md += ["---", "", "## %s　`%s`" % (q, qr["note"]), "",
               "- 画像：%s" % qr["user_profile"],
               "- 历史：%s" % (qr["history"] or "（无）"),
               "- 兴趣：`%s`" % (qr["interest_categories"] or "（无）"),
               "- 请求：%s" % qr["request"], ""]
        for i, r in enumerate(rr, 1):
            md.append("%d. **%s**　[%s] %s  \n   %s" % (
                i, r["title"], r["category"], r["published_at"], r["reason"]))
        md += ["", "**打分**：时效 __ 相关 __ 多样 __ 解释 __　备注：______", ""]
    (config.DATA_DIR / ("labels_%s.md" % args.tag)).write_text("\n".join(md), encoding="utf-8")
    print("已生成 %d 条：%s / %s" % (len(picked), out_csv.name, "labels_%s.md" % args.tag))


if __name__ == "__main__":
    main()
