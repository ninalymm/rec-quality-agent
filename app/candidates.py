"""候选池：加载、按评测日计算发布日期、把模型的选择补全成完整推荐。

设计要点：模型只输出 {id, reason}，标题/类目/日期由这里从池子里填。
这样输出里四个字段有三个不可能出错——只剩 reason 是模型自由发挥。
"""
import csv
from datetime import date, datetime, timedelta

from app import config

POOL_PATH = config.DATA_DIR / "candidates" / "pool_v1.csv"

# 受控词表：与 eval/rubric.md 保持一致
CATEGORIES = ("技术", "职场", "理财", "健康运动", "生活方式", "教育", "娱乐", "其他")


def today():
    """评测日：按 Asia/Shanghai 的当天。抽成函数便于测试时替换。"""
    return datetime.now().date()


def load_pool(path=None):
    path = path or POOL_PATH
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def published_at(age_days, eval_date):
    """候选池存的是相对天数，这里换算成绝对日期。"""
    return (eval_date - timedelta(days=int(age_days))).isoformat()


def enrich(items, pool, eval_date):
    """把 [{"id","reason"}] 补成完整推荐；未知 id 直接丢弃。"""
    by_id = {c["id"]: c for c in pool}
    out = []
    for item in items:
        c = by_id.get(item.get("id"))
        if c is None:
            continue
        out.append({
            "id": c["id"],
            "title": c["title"],
            "category": c["category"],
            "published_at": published_at(c["age_days"], eval_date),
            "reason": (item.get("reason") or "").strip(),
        })
    return out


def render_for_prompt(pool, eval_date, limit=None):
    """把候选池渲染成 prompt 里的一段文本。"""
    rows = pool[:limit] if limit else pool
    lines = []
    for c in rows:
        lines.append("%s | %s | %s | %s" % (
            c["id"], c["category"], published_at(c["age_days"], eval_date), c["title"]
        ))
    return "\n".join(lines)
