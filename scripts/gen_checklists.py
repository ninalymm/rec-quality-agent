"""给每条 query 生成「理想答案要点」（M1 的最后一件交付物）。

要点不是标准答案，而是 3–5 条**可判定**的检查项：judge 打分时对照它，
人工复核时也用它——没有它，judge 只能凭感觉给 3 分。

用法：
    python -m scripts.gen_checklists --limit 3    # 试跑
    python -m scripts.gen_checklists              # 全量（可断点续跑）
"""
import argparse
import csv
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from app import config
from app.llm import client_for, cost_cny

OUT = config.DATA_DIR / "checklists.jsonl"

SYSTEM = "你是推荐系统的评测设计者。只输出 JSON，不要解释。"

USER = """给定一个推荐任务，写出 3–4 条「理想推荐对这个用户来说应该满足什么」。

用户画像：{user_profile}
历史行为：{history}
兴趣类目：{interest}
用户请求：{request}

务必要点：
1. **只写这个用户/这个请求特有的期望**。以下内容系统已单独计算，不要重复写：
   条数是否等于 5、类目覆盖数、发布日期是否在 N 天内、理由是否引用历史标题
2. **每条不超过 30 字**，必须可判定（能回答「有没有」「几条」）
3. 结合画像里的具体处境（如正在跳槽、孩子在读小学），不要写对谁都成立的套话
4. 若历史为空、请求与兴趣冲突、或请求限制了条数/时间，只用一条说明「这种情况怎么算合格」
5. 不要写「若不足 5 条则补充候选」这类补救方案

输出 JSON：{{"points": ["...", "..."]}}
"""


def load_done():
    if not OUT.exists():
        return set()
    done = set()
    with open(OUT, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                done.add(json.loads(line)["qid"])
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条（试跑用）")
    ap.add_argument("--workers", type=int, default=6, help="并发数")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(config.DATA_DIR / "queries.csv", encoding="utf-8-sig")))
    done = load_done()
    todo = [r for r in rows if r["qid"] not in done]
    if args.limit:
        todo = todo[: args.limit]

    client, cfg = client_for()
    lock = threading.Lock()
    state = {"ok": 0, "fail": 0, "cost": 0.0}
    t0 = time.time()

    def work(r):
        msg = USER.format(
            user_profile=r["user_profile"],
            history=r["history"] or "（无）",
            interest=r["interest_categories"] or "（无）",
            request=r["request"],
        )
        resp = client.chat.completions.create(
            model=cfg["model"],
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": msg}],
            temperature=0.3,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        points = data.get("points") or []
        c = cost_cny(cfg, resp.usage)
        rec = {"qid": r["qid"], "points": points, "note": r["note"],
               "model": cfg["model"], "cost_cny": round(c, 6),
               "tokens": {"prompt": resp.usage.prompt_tokens,
                          "completion": resp.usage.completion_tokens}}
        with lock:
            with open(OUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            state["ok"] += 1
            state["cost"] += c
        return r["qid"], len(points)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(work, r): r["qid"] for r in todo}
        for n, fut in enumerate(as_completed(futures), 1):
            try:
                qid, np_ = fut.result()
                if not (3 <= np_ <= 4):
                    print("  [warn] %s 要点数 %d" % (qid, np_))
            except Exception as exc:
                with lock:
                    state["fail"] += 1
                print("  [fail] %s: %s" % (futures[fut], str(exc)[:90]))
            if n % 25 == 0:
                print("  进度 %d/%d，累计 ¥%.4f" % (n, len(todo), state["cost"]))

    print("\n完成 %d 条，失败 %d 条，耗时 %.1fs，总成本 ¥%.4f"
          % (state["ok"], state["fail"], time.time() - t0, state["cost"]))


if __name__ == "__main__":
    main()
