"""M3：规划 → 选工具 → 执行 → 判断完成。

设计取舍：
- 工具参数尽量少：agent 只需要 qid，其余从 state 里取。
  让模型传大段 JSON（比如 5 条推荐）既贵又容易错传。
- 用原生 function calling，不自己解析 JSON——省掉一层容错。
- 每步记录 trace（工具、参数、耗时、结果摘要），这是 M3 的验收点。
"""
import json
import time

from openai import BadRequestError

from app import candidates, config
from app.llm import client_for, cost_cny
from app.recs import generate_recs
from eval import judge as judge_mod

SYSTEM = """你是推荐质量 Agent。给定一个评测题号（qid），你的任务是：
1. 调用 generate_recs 生成 5 条推荐
2. 调用 metrics_calc 统计推荐的结构指标
3. 调用 score_with_rubric 按 rubric 打分
4. 用一句话总结结果（是否通过、总分、主要问题）

规则：
- 必须按 1→2→3 的顺序调用，三个工具都要用到
- 工具只需要 qid 参数，其余从上下文取
- 最多 6 步，完成后直接给结论"""

TOOLS = [
    {"type": "function", "function": {
        "name": "generate_recs",
        "description": "为指定 qid 的用户生成 5 条推荐",
        "parameters": {"type": "object", "properties": {
            "qid": {"type": "string", "description": "题号，如 Q001"}}, "required": ["qid"]}}},
    {"type": "function", "function": {
        "name": "metrics_calc",
        "description": "统计已生成推荐的结构指标（类目数、理由长度等）",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "score_with_rubric",
        "description": "按 eval/rubric.md 的四个维度对已生成的推荐打分",
        "parameters": {"type": "object", "properties": {}}}},
]


class TaskState:
    def __init__(self, qid):
        self.qid = qid
        self.recs = None
        self.metrics = None
        self.judgement = None


def _tool_generate(state):
    import csv
    rows = {r["qid"]: r for r in csv.DictReader(
        open(config.DATA_DIR / "queries.csv", encoding="utf-8-sig"))}
    q = rows[state.qid]
    out = generate_recs(q["user_profile"], q["history"], q["request"])
    state.recs = out["recommendations"]
    return {"count": len(state.recs),
            "titles": [r["title"] for r in state.recs],
            "cost_cny": out["cost_cny"]}


def _tool_metrics(state):
    if not state.recs:
        return {"error": "还没有生成推荐"}
    types = {}
    for r in state.recs:
        types[r["category"]] = types.get(r["category"], 0) + 1
    state.metrics = {
        "count": len(state.recs),
        "types": len(types),
        "type_dist": types,
        "avg_reason_len": round(sum(len(r["reason"]) for r in state.recs) / len(state.recs), 1),
    }
    return state.metrics


def _tool_score(state):
    if not state.recs:
        return {"error": "还没有生成推荐"}
    import csv
    rows = {r["qid"]: r for r in csv.DictReader(
        open(config.DATA_DIR / "queries.csv", encoding="utf-8-sig"))}
    res = judge_mod.judge(rows[state.qid], state.recs)
    state.judgement = res
    return {"dims": {k: v["score"] for k, v in res["dims"].items()},
            "summary": res["summary"],
            "scale": "四个维度各 0–2 分，总分 0–8；四维均 ≥1 才算通过"}


HANDLERS = {"generate_recs": lambda s, a: _tool_generate(s),
            "metrics_calc": lambda s, a: _tool_metrics(s),
            "score_with_rubric": lambda s, a: _tool_score(s)}


def run_task(qid, provider=None, max_steps=6, model=None):
    """跑一次任务，返回 result + trace + 成本。"""
    client, cfg = client_for(provider, model)
    state = TaskState(qid)
    trace = []
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": "请评测 %s" % qid}]
    total_cost = 0.0
    answer = ""

    for step in range(1, max_steps + 1):
        t0 = time.time()
        resp = client.chat.completions.create(
            model=cfg["model"], messages=messages, tools=TOOLS,
            tool_choice="auto", temperature=0, max_tokens=600)
        total_cost += cost_cny(cfg, resp.usage)
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            answer = msg.content or ""
            trace.append({"step": step, "tool": "(final)", "args": {},
                          "result": answer[:80], "latency_ms": int((time.time() - t0) * 1000)})
            break

        for call in msg.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            handler = HANDLERS.get(name)
            try:
                result = handler(state, args) if handler else {"error": "未知工具 %s" % name}
            except Exception as exc:
                result = {"error": "%s: %s" % (type(exc).__name__, str(exc)[:80])}
            trace.append({"step": step, "tool": name, "args": args,
                          "result": json.dumps(result, ensure_ascii=False)[:120],
                          "latency_ms": int((time.time() - t0) * 1000)})
            messages.append({"role": "tool", "tool_call_id": call.id,
                             "content": json.dumps(result, ensure_ascii=False)})

    if not answer and state.judgement:
        s = state.judgement["summary"]
        answer = "总分 %s，%s，%s" % (s["total"], s["grade"], "通过" if s["passed"] else "不通过")

    return {"qid": qid, "result": answer, "trace": trace,
            "steps": len(trace), "cost_cny": round(total_cost, 6),
            "recs": state.recs, "judgement": state.judgement}
