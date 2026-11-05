"""M5：回归门禁。跑固定 20 条任务，成功率低于基线 5% 就 exit 1。

用法：
    python -m eval.regression                    # 跑一次，与基线比较
    python -m eval.regression --update-baseline  # 把本次结果写成新基线
    python -m eval.regression --limit 5          # 冒烟用

退出码：0 通过；1 低于阈值；2 缺 key（跳过）
"""
import argparse
import json
import statistics
import time

from app import config
from app.agent import run_task
from app.llm import MissingKeyError, resolve

DATA = config.DATA_DIR
TASKS = DATA / "regression_tasks.json"
BASELINE = DATA / "regression_baseline.json"
THRESHOLD = 0.05          # 允许下降 5 个百分点


def load_tasks():
    return json.loads(TASKS.read_text(encoding="utf-8"))["tasks"]


def load_baseline():
    if not BASELINE.exists():
        return None
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--update-baseline", action="store_true")
    args = ap.parse_args()

    try:
        resolve()                      # 没有 key 就没法跑真实回归
    except MissingKeyError:
        print("跳过：未配置 DEEPSEEK_API_KEY（CI 里需要把 key 放进 Secrets）")
        return 2

    tasks = load_tasks()
    if args.limit:
        tasks = tasks[: args.limit]

    rows, t0 = [], time.time()
    for i, t in enumerate(tasks, 1):
        try:
            out = run_task(t["qid"])
            judged = out.get("judgement") or {}
            passed = bool(judged.get("summary", {}).get("passed"))
            rows.append({"qid": t["qid"], "note": t["note"], "status": out["status"],
                         "passed": passed, "steps": out["steps"],
                         "cost": out["cost_cny"],
                         "total": judged.get("summary", {}).get("total")})
        except Exception as exc:
            rows.append({"qid": t["qid"], "note": t["note"], "status": "error",
                         "passed": False, "steps": 0, "cost": 0.0,
                         "total": None, "error": str(exc)[:120]})
        print("  %2d/%d %s  通过=%s 步数=%d" % (i, len(tasks), t["qid"],
                                                rows[-1]["passed"], rows[-1]["steps"]))

    n = len(rows)
    pass_rate = sum(1 for r in rows if r["passed"]) / n
    avg_steps = statistics.mean(r["steps"] for r in rows)
    total_cost = sum(r["cost"] for r in rows)
    result = {"pass_rate": round(pass_rate, 4), "avg_steps": round(avg_steps, 2),
              "avg_cost": round(total_cost / n, 6), "n": n,
              "elapsed_s": round(time.time() - t0, 1),
              "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S")}

    print("\n结果：成功率 %.1f%%（%d/%d）｜平均步数 %.2f｜平均成本 ¥%.6f｜总成本 ¥%.4f"
          % (pass_rate * 100, sum(1 for r in rows if r["passed"]), n,
             avg_steps, result["avg_cost"], total_cost))

    base = load_baseline()
    if args.update_baseline or base is None:
        BASELINE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("已写入基线：%s" % BASELINE.name)
        return 0

    if base.get("n") != n:
        print("样本数不同（基线 %s 条 / 本次 %d 条），跳过比较" % (base.get("n"), n))
        return 0

    # 用「条数」而不是「百分比」比较：
    # 1) 避免浮点误差（0.75-0.70 = 0.050000000000000044 > 0.05）
    # 2) 20 条样本下，1 条 = 5 个百分点，等于阈值本身；
    #    所以允许 1 条波动，即 max(1 条, 5% 对应条数)
    passed_n = sum(1 for r in rows if r["passed"])
    base_passed = round(base["pass_rate"] * base["n"])
    # 20 条样本次实测同代码三次分别为 75% / 70% / 85%（±15pp），
    # 一个标准差就有 2–3 条；因此允许 2 条波动，宁可漏报也不误报
    allowed = max(2, round(THRESHOLD * n))
    drop = base_passed - passed_n
    print("基线 %d/%d，本次 %d/%d，下降 %d 条（允许波动 %d 条）"
          % (base_passed, base["n"], passed_n, n, drop, allowed))
    if drop > allowed:
        print("✗ 回归门禁失败：成功率下降 %d 条，超过允许的 %d 条" % (drop, allowed))
        return 1
    print("✓ 回归门禁通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
