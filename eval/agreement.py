"""双 judge 一致性分析。

只做计算，不调用模型：
- 每个维度的一致性（百分比 + Cohen's kappa）
- 分歧分布（哪些题目、差多少）
- 客观维度应恒为 1.0，作为流程自检

用法：
    python -m eval.agreement
"""
import json
from collections import Counter

from app import config

DIMS = ("timeliness", "relevance", "diversity", "explainability")


def _pairs(la, lb, dim):
    """取出两边都有值（非 null）的配对。"""
    out = []
    for x, y in zip(la, lb):
        sa, sb = x["dims"][dim]["score"], y["dims"][dim]["score"]
        if sa is not None and sb is not None:
            out.append((sa, sb))
    return out


def kappa(pairs):
    n = len(pairs)
    if n == 0:
        return None, None, None
    po = sum(1 for x, y in pairs if x == y) / n
    ca = Counter(x for x, _ in pairs)
    cb = Counter(y for _, y in pairs)
    pe = sum(ca[c] * cb[c] for c in set(ca) | set(cb)) / (n * n)
    if pe >= 1:
        return None, po, pe
    return (po - pe) / (1 - pe), po, pe


def load(provider):
    path = config.DATA_DIR / ("judged_%s.jsonl" % provider)
    if not path.exists():
        return {}
    return {json.loads(l)["qid"]: json.loads(l) for l in open(path, encoding="utf-8")}


def main():
    a = load("deepseek")
    b = load("qwen")
    common = [q for q in a if q in b]
    print("对比样本：%d 条\n" % len(common))

    print("%-16s %8s %10s %10s" % ("维度", "一致率", "kappa", "样本数"))
    print("-" * 48)
    for dim in DIMS:
        pairs = _pairs([a[q] for q in common], [b[q] for q in common], dim)
        k, po, pe = kappa(pairs)
        print("%-16s %7.1f%% %10s %10d" % (
            dim, po * 100 if po is not None else 0,
            "%.3f" % k if k is not None else "n/a", len(pairs)))

    # 分歧明细（只看可解释性，另外三维理论上应为 1.0）
    diffs = []
    for q in common:
        sa = a[q]["dims"]["explainability"]["score"]
        sb = b[q]["dims"]["explainability"]["score"]
        if sa != sb:
            diffs.append((q, sa, sb, a[q]["note"]))
    print("\n可解释性分歧 %d 条：" % len(diffs))
    for q, sa, sb, note in diffs[:10]:
        print("  %s [%s] deepseek=%s qwen=%s" % (q, note, sa, sb))

    # 总分差异
    td = [(a[q]["summary"]["total"], b[q]["summary"]["total"]) for q in common
          if a[q]["summary"]["total"] is not None and b[q]["summary"]["total"] is not None]
    if td:
        same = sum(1 for x, y in td if x == y)
        print("\n总分一致 %.1f%%（%d/%d）" % (same / len(td) * 100, same, len(td)))
        print("总分均值：deepseek %.2f / qwen %.2f" % (
            sum(x for x, _ in td) / len(td), sum(y for _, y in td) / len(td)))


if __name__ == "__main__":
    main()
