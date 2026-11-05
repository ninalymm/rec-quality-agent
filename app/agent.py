"""M3：规划 → 选工具 → 执行 → 判断完成。

设计要点：
- 工具的参数只传 qid，其余数据从内存 state 取（模型擅长判断，不擅长搬运）
- 工具的依赖用 requires / provides 声明，不在每个工具里硬写 if
  缺前置时返回可执行的 error + hint，模型据此自愈
- 每步记录 trace，含 ok / error，可统计模型最容易搞错哪一步
"""
import csv
import json
import time

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
- 工具只需要 qid 参数，其余从上下文取
- 如果工具返回缺少前置数据，按提示先补做
- 最多 6 步，完成后直接给结论"""


class TaskState:
    def __init__(self, qid):
        self.qid = qid
        self.recs = None
        self.metrics = None
        self.judgement = None


def _load_query(qid):
    rows = {r["qid"]: r for r in csv.DictReader(
        open(config.DATA_DIR / "queries.csv", encoding="utf-8-sig"))}
    return rows[qid]


def _tool_generate(state, args=None):
    q = _load_query(state.qid)
    out = generate_recs(q["user_profile"], q["history"], q["request"])
    state.recs = out["recommendations"]
    return {"count": len(state.recs),
            "titles": [r["title"] for r in state.recs],
            "cost_cny": out["cost_cny"]}


def _tool_metrics(state, args=None):
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


def _tool_score(state, args=None):
    q = _load_query(state.qid)
    res = judge_mod.judge(q, state.recs)
    state.judgement = res
    return {"dims": {k: v["score"] for k, v in res["dims"].items()},
            "summary": res["summary"],
            "scale": "四个维度各 0–2 分，总分 0–8；四维均 ≥1 才算通过"}


# requires / provides 声明依赖；schema 用来生成 function calling 的说明书
TOOL_SPECS = {
    "generate_recs": {
        "description": "为指定 qid 的用户生成 5 条推荐",
        "requires": (),
        "provides": ("recs",),
        "parameters": {"type": "object",
                       "properties": {"qid": {"type": "string", "description": "题号，如 Q001"}},
                       "required": ["qid"]},
        "handler": _tool_generate,
    },
    "metrics_calc": {
        "description": "统计已生成推荐的结构指标（类目数、理由长度等）",
        "requires": ("recs",),
        "provides": ("metrics",),
        "parameters": {"type": "object", "properties": {}},
        "handler": _tool_metrics,
    },
    "score_with_rubric": {
        "description": "按 eval/rubric.md 的四个维度对已生成的推荐打分",
        "requires": ("recs",),
        "provides": ("judgement",),
        "parameters": {"type": "object", "properties": {}},
        "handler": _tool_score,
    },
}

TOOLS = [{"type": "function",
          "function": {"name": name, "description": spec["description"],
                       "parameters": spec["parameters"]}}
         for name, spec in TOOL_SPECS.items()]


def _missing(state, spec):
    return [k for k in spec["requires"] if getattr(state, k, None) in (None, (), "", [])]


def _provider_for(keys):
    for name, spec in TOOL_SPECS.items():
        if set(keys) & set(spec["provides"]):
            return name
    return None


def dispatch(name, state, args):
    """执行一次工具调用。返回 {ok, data} 或 {ok: False, error, hint}。"""
    spec = TOOL_SPECS.get(name)
    if spec is None:
        return {"ok": False, "error": "未知工具 %s" % name,
                "hint": "可用工具: %s" % ", ".join(TOOL_SPECS)}
    missing = _missing(state, spec)
    if missing:
        provider = _provider_for(missing)
        return {"ok": False,
                "error": "缺少前置数据: %s" % ", ".join(missing),
                "hint": ("请先调用 %s" % provider) if provider else "无法自动修复"}
    try:
        return {"ok": True, "data": spec["handler"](state, args)}
    except Exception as exc:
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, str(exc)[:80]),
                "hint": "检查参数或重试"}


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
            trace.append({"step": step, "tool": "(final)", "args": {}, "ok": True,
                          "error": None, "result": answer[:80],
                          "latency_ms": int((time.time() - t0) * 1000)})
            break

        for call in msg.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            res = dispatch(name, state, args)
            payload = res.get("data") if res["ok"] else {"error": res["error"], "hint": res.get("hint")}
            trace.append({"step": step, "tool": name, "args": args, "ok": res["ok"],
                          "error": None if res["ok"] else res["error"],
                          "result": json.dumps(payload, ensure_ascii=False)[:120],
                          "latency_ms": int((time.time() - t0) * 1000)})
            messages.append({"role": "tool", "tool_call_id": call.id,
                             "content": json.dumps(payload, ensure_ascii=False)})

    if not answer and state.judgement:
        s = state.judgement["summary"]
        answer = "总分 %s，%s，%s" % (s["total"], s["grade"], "通过" if s["passed"] else "不通过")

    return {"qid": qid, "result": answer, "trace": trace,
            "steps": len(trace), "cost_cny": round(total_cost, 6),
            "tool_errors": sum(1 for t in trace if not t["ok"]),
            "recs": state.recs, "judgement": state.judgement}
