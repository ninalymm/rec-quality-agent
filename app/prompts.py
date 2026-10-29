"""Prompt 模板集中管理。

为什么单独拆一个文件：
- M1/M2 会反复调 prompt（加评分维度、补反例、做 A/B 位置偏差实验），改文案不该碰业务代码
- 以后要记录「哪个 prompt 版本对应哪次评测」，模板集中才管得住
"""

RECS_SYSTEM = (
    "你是内容推荐系统的推荐策略模块。"
    "根据用户画像和历史行为，产出恰好 {count} 条内容推荐。"
    "只输出 JSON，不要 markdown 代码块，不要解释。"
)

RECS_USER = """用户画像：
{user_profile}

最近历史行为：
{history}

本次请求：
{request}

输出 JSON，结构：
{{"recommendations": [
  {{"title": "标题",
    "category": "类别",
    "freshness": "new|recent|old",
    "reason": "为什么推荐给这个用户，要能对上画像或历史里的具体点"}}
]}}
"""


def build_recs_messages(user_profile, history, request, count=5):
    """拼出 chat completion 的 messages。纯函数，方便单测。"""
    return [
        {"role": "system", "content": RECS_SYSTEM.format(count=count)},
        {
            "role": "user",
            "content": RECS_USER.format(
                user_profile=user_profile, history=history, request=request
            ),
        },
    ]
