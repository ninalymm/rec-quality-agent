"""M0 验收：把「环境 + 能跑通一次调用」拆成可执行的检查项。

用法：
    python -m scripts.check_m0              # 结构层检查（不需要 key）
    python -m scripts.check_m0 --live       # 额外做一次真实调用，评估输出质量
    python -m scripts.check_m0 --live -n 3  # 连续调用 3 次，看稳定性

退出码：0 全部通过；1 有失败项；2 结构层通过但缺 key，实时检查被跳过。
"""
import argparse
import platform
import subprocess
import sys

from app import config
from app.llm import PROVIDERS, MissingKeyError, resolve
from app.prompts import build_recs_messages
from app.recs import _extract_recs, _loads

OK, BAD, WARN, SKIP = "[✓]", "[✗]", "[!]", "[–]"
results = []   # (是否通过, 分节, 描述, 详情)


def check(ok, section, desc, detail=""):
    # 归一成布尔：像 `cond and recs` 这种表达式会返回列表而不是 True，
    # 统计用的是 `ok is True`，不归一就会漏计。
    ok = bool(ok)
    results.append((ok, section, desc, detail))
    print("  %s %s%s" % (OK if ok else BAD, desc, ("  ← " + detail) if detail else ""))


def check_skip(section, desc, detail=""):
    """缺少前置条件（比如没有 key）：既不算通过也不算失败。"""
    results.append((None, section, desc, detail))
    print("  %s %s%s" % (SKIP, desc, ("  ← " + detail) if detail else ""))


def head(title):
    print("\n" + title)
    print("-" * 62)


def section_env():
    head("环境")
    v = sys.version_info
    arch = platform.machine()
    check(v >= (3, 10), "环境", "Python >= 3.10",
          "%d.%d.%d" % (v[0], v[1], v[2]))
    check(arch in ("arm64", "x86_64"), "环境", "解释器架构可识别", arch)
    if arch == "x86_64" and platform.platform().lower().find("arm") >= 0:
        check(False, "环境", "非 Rosetta x86_64", arch)

    for mod in ("openai", "dotenv", "pandas", "fastapi", "pytest", "uvicorn"):
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", "?")
            check(True, "环境", "依赖可导入: %s" % mod, str(ver))
        except Exception as exc:
            check(False, "环境", "依赖可导入: %s" % mod, str(exc)[:60])

    try:
        import app  # noqa: F401
        check(True, "环境", "import app 通过")
    except Exception as exc:
        check(False, "环境", "import app 通过", str(exc)[:60])


def section_config():
    head("配置与链路")
    name = config.DEFAULT_PROVIDER
    check(name in PROVIDERS, "配置", "默认 provider 已注册", name)

    got = None
    try:
        resolve("deepseek")
    except MissingKeyError:
        got = "missing-key"
    except Exception as exc:
        got = "error: %s" % exc
    else:
        got = "has-key"
    check(got in ("missing-key", "has-key"), "配置", "缺 key 时行为可控", got)

    msgs = build_recs_messages("p", "h", "r", count=5)
    check(len(msgs) == 2 and "5" in msgs[0]["content"], "配置",
          "prompt 构造含条数约束", "%d 条消息" % len(msgs))

    check(_loads('```json\n{"recommendations": []}\n```') == {"recommendations": []},
          "配置", "JSON 解析兼容代码围栏")
    check(_extract_recs({"recommendations": [{"title": "a"}]}) != [],
          "配置", "返回结构提取正常")


def section_repo():
    head("仓库")
    from pathlib import Path
    root = config.ROOT
    need = ["app", "eval", "data", "tests", "scripts", ".github/workflows"]
    missing = [d for d in need if not (root / d).exists()]
    check(not missing, "仓库", "目录结构齐全", "缺: %s" % missing if missing else "")

    gi = (root / ".gitignore").read_text(encoding="utf-8") if (root / ".gitignore").exists() else ""
    check(".env" in gi, "仓库", ".gitignore 排除 .env")
    check(".venv" in gi, "仓库", ".gitignore 排除 .venv")

    remote = subprocess.run(["git", "remote", "get-url", "origin"],
                            capture_output=True, text=True, cwd=root).stdout.strip()
    check(bool(remote), "仓库", "origin 已配置", remote)
    if remote:
        check(remote.startswith("git@"), "仓库", "origin 使用 SSH（避开 443 阻断）", remote)

    ahead = subprocess.run(["git", "rev-list", "--count", "origin/main..HEAD"],
                           capture_output=True, text=True, cwd=root).stdout.strip()
    check(ahead == "0", "仓库", "本地与远端同步", "领先 %s 个 commit" % ahead if ahead else "")


def section_docs():
    """文档检查：README 里的 shell 命令必须能通过语法解析（不执行）。"""
    head("文档")
    readme = config.ROOT / "README.md"
    check(readme.exists(), "文档", "README 存在",
          "%d 行" % len(readme.read_text(encoding="utf-8").splitlines()) if readme.exists() else "")
    if not readme.exists():
        return

    import re
    text = readme.read_text(encoding="utf-8")
    blocks = re.findall(r"```bash\n(.*?)```", text, re.S)
    check(bool(blocks), "文档", "README 含 bash 示例", "%d 段" % len(blocks))

    bad = []
    for i, block in enumerate(blocks, 1):
        proc = subprocess.run(["bash", "-n"], input=block,
                              capture_output=True, text=True)
        if proc.returncode != 0:
            bad.append("第 %d 段: %s" % (i, proc.stderr.strip()[:70]))
    check(not bad, "文档", "README 命令语法合法", "；".join(bad))


def section_tests():
    head("测试")
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q"],
                          capture_output=True, text=True, cwd=config.ROOT)
    tail = [l for l in proc.stdout.strip().splitlines() if "passed" in l or "failed" in l]
    check(proc.returncode == 0, "测试", "pytest 全绿", tail[-1] if tail else "")


def evaluate_output(out, count):
    """对一次真实调用的输出做质量评估。"""
    recs = out["recommendations"]
    check(len(recs) == count, "质量", "条数符合预期", "%d/%d" % (len(recs), count))

    fields = ("title", "category", "reason", "freshness")
    complete = [r for r in recs if all(r.get(f) for f in fields)]
    check(len(complete) == len(recs) and recs, "质量", "字段完整(title/category/reason/freshness)",
          "%d/%d" % (len(complete), len(recs)))

    legal = [r for r in recs if r.get("freshness") in ("new", "recent", "old")]
    check(len(legal) == len(recs) and recs, "质量", "freshness 取值合法",
          "%d/%d" % (len(legal), len(recs)))

    cats = {r.get("category") for r in recs if r.get("category")}
    check(len(cats) >= 3, "质量", "类目多样性 >= 3", "%d 类: %s" % (len(cats), ",".join(sorted(cats))))

    lens = [len(r.get("reason", "")) for r in recs]
    avg = sum(lens) / len(lens) if lens else 0
    check(avg >= 20, "质量", "理由平均长度 >= 20 字", "%.1f 字" % avg)

    # 启发式：理由里是否出现画像/历史中的词（2 字以上）
    ctx = (config_prompt_text() or "")
    hits = 0
    for r in recs:
        reason = r.get("reason", "")
        if any(w in reason for w in _words(ctx)):
            hits += 1
    check(hits >= len(recs) // 2, "质量", "理由引用了画像/历史（启发式）",
          "%d/%d" % (hits, len(recs)))

    print("\n成本：tokens prompt=%d completion=%d，¥%.6f"
          % (out["tokens"]["prompt"], out["tokens"]["completion"], out["cost_cny"]))


def config_prompt_text():
    try:
        return build_recs_messages(DEMO["user_profile"], DEMO["history"], DEMO["request"], 5)[1]["content"]
    except Exception:
        return ""


def _words(text):
    """粗分词：按非汉字/字母数字切，取长度 >= 2 的片段。"""
    import re
    return [w for w in re.split(r"[^\u4e00-\u9fa5A-Za-z0-9]+", text) if len(w) >= 2]


DEMO = {
    "user_profile": "28 岁，上海，后端工程师，最近在准备跳槽；喜欢技术深度文，也看职场和跑步。",
    "history": "1) 《Go 内存模型详解》 2) 《上海互联网公司薪资对比》 3) 《跑步膝伤怎么恢复》",
    "request": "给我推荐 5 条今天可以看的内容",
}


def section_live(repeat):
    head("输出质量（实时调用）")
    if repeat <= 0:
        check_skip("质量", "真实调用", "repeat=0，未执行")
        return
    try:
        resolve()
    except MissingKeyError:
        check_skip("质量", "真实调用", "未配置 key —— 填好 .env 后重跑 --live")
        print("　　结构层检查不受影响；实时调用需要 DEEPSEEK_API_KEY 或 DASHSCOPE_API_KEY。")
        return

    from app.recs import generate_recs
    outs = []
    for i in range(repeat):
        try:
            out = generate_recs(DEMO["user_profile"], DEMO["history"], DEMO["request"])
            outs.append(out)
            print("  第 %d 次调用：%d 条，¥%.6f"
                  % (i + 1, len(out["recommendations"]), out["cost_cny"]))
        except Exception as exc:
            msg = " ".join(str(exc).split())   # 多行错误压成一行
            print("  第 %d 次调用失败：%s" % (i + 1, msg[:120]))
    if not outs:
        check(False, "质量", "真实调用成功", "全部失败")
        return
    check(len(outs) == repeat, "质量", "调用成功率", "%d/%d" % (len(outs), repeat))
    evaluate_output(outs[0], config.RECS_COUNT)


def main(argv=None):
    parser = argparse.ArgumentParser(description="M0 验收检查")
    parser.add_argument("--live", action="store_true", help="做真实调用并评估输出")
    parser.add_argument("-n", "--repeat", type=int, default=1, help="实时调用次数")
    args = parser.parse_args(argv)

    section_env()
    section_config()
    section_repo()
    section_docs()
    section_tests()
    if args.live:
        section_live(args.repeat)

    head("汇总")
    total = len(results)
    passed = sum(1 for ok, *_ in results if ok is True)
    failed = sum(1 for ok, *_ in results if ok is False)
    skipped = sum(1 for ok, *_ in results if ok is None)
    for section in ("环境", "配置", "仓库", "文档", "测试", "质量"):
        items = [r for r in results if r[1] == section]
        if not items:
            continue
        bad = [r for r in items if r[0] is False]
        skip = [r for r in items if r[0] is None]
        extra = ("，跳过 %d" % len(skip)) if skip else ""
        print("  %-6s %d 项，失败 %d%s" % (section, len(items), len(bad), extra))
    print("\n通过 %d/%d（失败 %d，跳过 %d）" % (passed, total - skipped, failed, skipped))

    if failed:
        print("M0 结论：有 %d 项未通过" % failed)
        return 1
    if skipped:
        print("M0 结论：结构层 PASS，输出质量待验证 —— 补 .env 后重跑 --live")
        return 2
    print("M0 结论：PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
