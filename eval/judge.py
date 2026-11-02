"""双 judge 打分器。

设计依据 eval/rubric.md：
- 维度1/2/3 由代码计算（日期、类目命中、类型数），不交给模型
- 维度4（理由可解释性）交给 LLM，这是唯一的语义维度

judge 不直接输出总分——先输出每条的判定标签，分数由代码算，
避免模型做算术（它经常算错 5 以内的加法）。
"""
import json
from datetime import date
from statistics import median

from openai import BadRequestError

from app import candidates, config
from app.llm import client_for, cost_cny

DIMS = ("timeliness", "relevance", "diversity", "explainability")
GRADES = ((7, "优秀"), (5, "合格"), (3, "待改进"), (0, "不合格"))


def _band(days):
    if days <= 30:
        return 2
    if days <= 60:
        return 1
    return 0


def score_timeliness(recs, eval_date):
    """5 条按中位数定档；可判定条目 <3 时记 null。"""
    days = []
    for r in recs:
        try:
            d = date.fromisoformat(r.get("published_at") or "")
        except ValueError:
            continue
        days.append((eval_date - d).days)
    if len(days) < 3:
        return {"score": None, "evidence": "可判定日期不足 3 条（%d 条）" % len(days)}
    m = median(days)
    return {"score": _band(m), "evidence": "5 条日期中位数 %d 天" % m}


def score_relevance(recs, interest_categories):
    wanted = {c.strip() for c in (interest_categories or "").split(";") if c.strip()}
    if not wanted:
        return {"score": None, "evidence": "用户无已表达兴趣（无历史行为）"}
    hits = [r for r in recs if r.get("category") in wanted]
    n = len(hits)
    return {"score": 2 if n >= 4 else (1 if n >= 2 else 0),
            "evidence": "%d/%d 条命中 %s" % (n, len(recs), "、".join(sorted(wanted)))}


def score_diversity(recs):
    types = {r.get("category") for r in recs if r.get("category")}
    n = len(types)
    return {"score": 2 if n >= 3 else (1 if n == 2 else 0),
            "evidence": "%d 个类型：%s" % (n, "、".join(sorted(types)))}


EXPLAIN_SYSTEM = "你是推荐质量的评审员。只输出 JSON，不要解释。"

EXPLAIN_USER = """用户的历史行为（判断依据）：
{history}

下面是 {n} 条推荐各自的理由：
{reasons}

请逐条判断每个理由属于哪一类：
- "specific"：指向历史中的**具体条目**（提到具体标题，或其中提到的具体事件/观点），可核对
- "category"：只提到方向或类目（如「你在关注技术领域」「和你的兴趣相关」），任何同类用户都适用
- "vague"：没有指向（如「根据您的历史行为推荐」「猜你喜欢」）

注意：只要理由里出现了历史中的具体标题，就判 specific，哪怕语气平淡。

输出 JSON：
{{"labels": ["specific 或 category 或 vague", ...{n} 个], "evidence": "一句话说明哪条最弱"}}
"""


def judge_explainability(recs, history, provider=None, model=None):
    """唯一需要语义判断的维度：返回 score + evidence + 逐条标签。"""
    if not recs:
        return {"score": 0, "evidence": "无推荐内容", "labels": []}
    client, cfg = client_for(provider, model)
    reasons = "\n".join("%d. %s" % (i + 1, r.get("reason") or "（空）")
                        for i, r in enumerate(recs))
    msg = EXPLAIN_USER.format(history=history or "（无历史）", n=len(recs), reasons=reasons)
    kwargs = dict(model=cfg["model"],
                  messages=[{"role": "system", "content": EXPLAIN_SYSTEM},
                            {"role": "user", "content": msg}],
                  temperature=0.0, max_tokens=400)
    try:
        resp = client.chat.completions.create(response_format={"type": "json_object"}, **kwargs)
    except BadRequestError:
        resp = client.chat.completions.create(**kwargs)

    data = json.loads(resp.choices[0].message.content)
    labels = data.get("labels") or []
    labels = [l if l in ("specific", "category", "vague") else "vague" for l in labels]
    specific = sum(1 for l in labels if l == "specific")
    score = 2 if specific >= 4 else (1 if specific >= 2 else 0)
    return {
        "score": score,
        "evidence": data.get("evidence") or "%d 条引用了具体历史" % specific,
        "labels": labels,
        "specific_count": specific,
        "cost_cny": round(cost_cny(cfg, resp.usage), 6),
        "model": cfg["model"],
    }


def aggregate(dims):
    """四维均 ≥1 为通过；任一 null 不参与判定，总分也记 null。"""
    scores = {k: dims[k]["score"] for k in DIMS}
    values = [v for v in scores.values() if v is not None]
    passed = bool(values) and all(v >= 1 for v in values)
    total = sum(values) if len(values) == len(DIMS) else None
    grade = None
    if total is not None:
        for floor, name in GRADES:
            if total >= floor:
                grade = name
                break
    return {"passed": passed, "total": total, "grade": grade,
            "partial": len(values) != len(DIMS)}


def judge(query_row, recs, provider=None, model=None, eval_date=None):
    """对一组推荐打四维分。query_row 需含 history / interest_categories。"""
    eval_date = eval_date or candidates.today()
    dims = {
        "timeliness": score_timeliness(recs, eval_date),
        "relevance": score_relevance(recs, query_row.get("interest_categories")),
        "diversity": score_diversity(recs),
    }
    exp = judge_explainability(recs, query_row.get("history", ""), provider, model)
    dims["explainability"] = {k: exp[k] for k in ("score", "evidence")}
    return {"qid": query_row.get("qid"), "dims": dims,
            "summary": aggregate(dims),
            "explain_labels": exp["labels"],
            "cost_cny": exp.get("cost_cny", 0.0),
            "model": exp.get("model")}
