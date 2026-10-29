"""M0 验收脚本：跑通一次「生成 5 条推荐」的调用。

用法：
    python -m scripts.smoke_recs                # 用 .env 里的 provider（默认 deepseek）
    python -m scripts.smoke_recs --provider qwen
    python -m scripts.smoke_recs --dry-run      # 不联网，只检查配置和 prompt

退出码：0 成功；1 条数不对 / 连接失败；2 缺 key / key 无效。
"""
import argparse
import os
import sys

from openai import APIConnectionError, AuthenticationError

from app import config
from app.llm import PROVIDERS, MissingKeyError
from app.prompts import build_recs_messages

DEMO = {
    "user_profile": "28 岁，上海，后端工程师，最近在准备跳槽；喜欢技术深度文，也看职场和跑步。",
    "history": "1) 《Go 内存模型详解》 2) 《上海互联网公司薪资对比》 3) 《跑步膝伤怎么恢复》",
    "request": "给我推荐 5 条今天可以看的内容",
}


def mask(key):
    if not key:
        return "（未设置）"
    return key[:6] + "..." + key[-4:] if len(key) > 12 else "（已设置）"


def dry_run(provider, model, count):
    name = provider or config.DEFAULT_PROVIDER
    if name not in PROVIDERS:
        print("未知 provider: %r，可选：%s" % (name, ", ".join(sorted(PROVIDERS))))
        return 2
    cfg = PROVIDERS[name]
    key = os.getenv(cfg["key_env"], "").strip()
    if not key and cfg.get("default_key"):
        key = cfg["default_key"]
        shown = "内置占位符（该 provider 不校验）"
    else:
        shown = mask(key)
    print("[dry-run] provider = %s" % name)
    print("[dry-run] base_url = %s" % cfg["base_url"])
    print("[dry-run] model    = %s" % (model or cfg["model"]))
    print("[dry-run] key env  = %s -> %s" % (cfg["key_env"], shown))
    if not key:
        print("\n⚠ 没有 key，真实调用会失败。填好 .env 后去掉 --dry-run 再跑。")
    messages = build_recs_messages(**DEMO, count=count)
    print("\n[dry-run] prompt 共 %d 条消息，%d 字符" % (
        len(messages), sum(len(m["content"]) for m in messages)
    ))
    print("-" * 60)
    print(messages[1]["content"][:400] + " ...")
    print("-" * 60)
    print("[dry-run] 管线 OK：配置、prompt 构造、JSON 解析函数都可导入。")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="M0：跑通一次生成 5 条推荐")
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default=None)
    parser.add_argument("--model", default=None, help="覆盖默认模型名")
    parser.add_argument("--count", type=int, default=config.RECS_COUNT)
    parser.add_argument("--dry-run", action="store_true", help="不联网，只检查配置")
    args = parser.parse_args(argv)

    if args.dry_run:
        return dry_run(args.provider, args.model, args.count)

    from app.recs import generate_recs  # 懒导入：dry-run 不需要 openai 的真正调用路径

    try:
        out = generate_recs(
            DEMO["user_profile"], DEMO["history"], DEMO["request"],
            provider=args.provider, model=args.model, count=args.count,
        )
    except MissingKeyError as exc:
        print("✗ %s" % exc)
        return 2
    except AuthenticationError:
        print("✗ key 无效或已过期。到控制台重新生成，再更新 .env 里的 %s"
              % PROVIDERS[args.provider or config.DEFAULT_PROVIDER]["key_env"])
        return 2
    except APIConnectionError as exc:
        print("✗ 连不上 API（检查网络/代理）：%s" % exc)
        return 1

    recs = out["recommendations"]
    print("provider=%s model=%s" % (out["provider"], out["model"]))
    print("=" * 70)
    for i, rec in enumerate(recs, 1):
        print("%d. %s  [%s / %s]" % (
            i, rec.get("title", "(无标题)"),
            rec.get("category", "?"), rec.get("freshness", "?"),
        ))
        print("   理由：%s" % rec.get("reason", "(无)"))
    print("=" * 70)
    print("条数：%d（期望 %d）" % (len(recs), args.count))
    print("tokens：prompt=%d completion=%d" % (
        out["tokens"]["prompt"], out["tokens"]["completion"]
    ))
    print("成本估算：¥%.6f" % out["cost_cny"])
    return 0 if len(recs) == args.count else 1


if __name__ == "__main__":
    sys.exit(main())
