"""输出校验：把 rubric 里「能用代码判」的项先查一遍。

这不是 judge，只是机械检查——它替 M2 挡掉最脏的那部分数据：
条数不对、类目越界、日期非法、理由空泛到没有引用任何历史条目。

用法：
    from app import validate
    report = validate.check(out["recommendations"], pool, eval_date, history=history)
"""
import re
from datetime import date

from app.candidates import CATEGORIES

TITLE_RE = re.compile(r"《([^》]+)》")


def cited_titles(history):
    """从历史文本里抽出《...》中的标题。"""
    return TITLE_RE.findall(history or "")


def cites_any(reason, titles):
    """理由里是否出现了历史中的某个具体标题。"""
    return any(t and t in (reason or "") for t in titles)


def check(recs, pool, eval_date, count=5, history="", interest_categories=""):
    errors, warnings = [], []

    if len(recs) != count:
        errors.append("条数 %d != %d" % (len(recs), count))

    ids = [r.get("id") for r in recs]
    if len(set(ids)) != len(ids):
        errors.append("id 重复: %s" % ids)
    unknown = [i for i in ids if i not in {c["id"] for c in pool}]
    if unknown:
        errors.append("id 不在候选池: %s" % unknown)

    bad_cat = [r.get("category") for r in recs if r.get("category") not in CATEGORIES]
    if bad_cat:
        errors.append("类目越界: %s" % bad_cat)

    for r in recs:
        try:
            d = date.fromisoformat(r.get("published_at") or "")
        except ValueError:
            errors.append("日期无法解析: %r" % r.get("published_at"))
            continue
        if d > eval_date:
            errors.append("日期在未来: %s" % r.get("published_at"))

    for r in recs:
        if len((r.get("reason") or "").strip()) < 10:
            errors.append("理由过短或为空: %s" % r.get("id"))

    titles = cited_titles(history)
    cites = sum(1 for r in recs if cites_any(r.get("reason"), titles))
    if titles and cites == 0:
        warnings.append("没有任何一条理由引用了历史中的具体标题")

    types = len({r.get("category") for r in recs})
    if types < 3:
        warnings.append("类目数 %d < 3，多样性维度拿不到 2 分" % types)

    if interest_categories:
        wanted = {c.strip() for c in interest_categories.split(";") if c.strip()}
        hits = sum(1 for r in recs if r.get("category") in wanted)
        if hits < 4:
            warnings.append("兴趣命中 %d 条 < 4，相关性维度拿不到 2 分" % hits)

    stats = {
        "count": len(recs),
        "types": types,
        "cites": cites,
        "avg_reason_len": round(
            sum(len(r.get("reason") or "") for r in recs) / len(recs), 1
        ) if recs else 0,
    }
    return {"ok": not errors, "errors": errors, "warnings": warnings, "stats": stats}
