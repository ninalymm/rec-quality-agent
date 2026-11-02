"""Prompt 模板集中管理。

为什么单独拆一个文件：
- M1/M2 会反复调 prompt（加评分维度、补反例、做 A/B 位置偏差实验），改文案不该碰业务代码
- 以后要记录「哪个 prompt 版本对应哪次评测」，模板集中才管得住

v2 的改动（2026-11-02）：
- 从「自由生成」改成「从候选池里挑」：标题/类目/日期由代码填充，模型只给 id 和理由
- 理由从软约束（"对上画像里的具体点"）改成硬约束（必须出现历史里的具体标题）
"""
from app.candidates import CATEGORIES

RECS_SYSTEM = (
    "你是内容推荐系统的推荐策略模块。"
    "你只能从给定候选池中挑选内容，不得自行创作标题。"
    "选出恰好 {count} 条，并为每条写出推荐理由。只输出 JSON，不要解释。"
)

RECS_USER = """用户画像：
{user_profile}

最近历史行为：
{history}

本次请求：
{request}

候选池（只能从中挑，用 id 引用）：
{candidates}

要求：
1. 恰好选 {count} 条，id 必须来自上面的候选池，不能重复
2. 不要输出标题、类目、日期——这些由系统按候选池填充
3. 理由必须点出用户历史里的**具体标题**，例如「你在看《Go 内存模型详解》」
4. 不允许只写方向（如「你在关注技术领域」「根据您的历史推荐」），这类理由在评分时记 0 分
5. 尽量让 {count} 条覆盖 {min_types} 个以上不同的类目

输出 JSON：
{{"recommendations": [{{"id": "C001", "reason": "为什么推荐这条给这个用户"}}]}}
"""


def build_recs_messages(user_profile, history, request, candidates_text, count=5, min_types=3):
    """拼出 chat completion 的 messages。纯函数，方便单测。"""
    if not (history or "").strip():
        # 无历史时若不加约束，模型会编造「你看过…」来满足第 3 条要求
        history = ("（该用户没有任何历史行为）\n"
                   "注意：理由中禁止出现「你看过」「你读过」「你关注过」这类表述，"
                   "只能基于用户画像和本次请求来说明为什么推荐。")
    return [
        {"role": "system", "content": RECS_SYSTEM.format(count=count)},
        {
            "role": "user",
            "content": RECS_USER.format(
                user_profile=user_profile,
                history=history,
                request=request,
                candidates=candidates_text,
                count=count,
                min_types=min_types,
            ),
        },
    ]


__all__ = ["build_recs_messages", "CATEGORIES"]
