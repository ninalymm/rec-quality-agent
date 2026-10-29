# 缺陷记录（M0 阶段）

> 范围：M0 期间**自己写的代码**发现的缺陷。
> 环境、网络、工具链的坑另见 [troubleshooting.md](troubleshooting.md)。
>
> 状态说明：`已修` = 代码已改且验证；`待办` = 已定位但需要人工操作。

## 总览

| ID | 缺陷 | 严重度 | 发现方式 | 状态 |
|---|---|---|---|---|
| BUG-001 | 认证失败时直接抛原始 traceback | 中 | 用假 key 主动测试 | 已修 |
| BUG-002 | `--dry-run` 对 ollama 误报「没有 key」 | 低 | 跑 ollama 分支 | 已修 |
| BUG-003 | 部分兼容端点不支持 `response_format` 会 400 | 中 | 设计预判 + ollama | 已修 |
| BUG-004 | 缺 key 被报成「失败」而非「跳过」 | 中 | 用户跑 `--live -n 3` | 已修 |
| BUG-005 | 多行错误被截断成半句话 | 低 | 同上 | 已修 |
| BUG-006 | 统计漏计，显示 `26/28` | 高 | 用户跑 `--live` | 已修 |
| BUG-007 | git 身份缺失导致 commit 失败 | 中 | commit 时报错 | 部分修 |
| BUG-008 | `.DS_Store` 未被忽略 | 低 | `git status` | 已修 |

---

## BUG-001 认证失败时直接抛原始 traceback

**现象**：用无效 key 调用，终端打印十几行 openai SDK 内部堆栈，最后才是 `AuthenticationError: 401`。

**发现**：主动用假 key 跑 `smoke_recs`，目的是验证「请求真的发出去了」。

**根因**：只捕获了自定义的 `MissingKeyError`，没捕获 SDK 的 `AuthenticationError` / `APIConnectionError`。

**修复**：`scripts/smoke_recs.py` 增加两个 except，输出「key 无效」或「连不上 API」。

**防复发**：`check_m0` 里加了「缺 key 时行为可控」检查项——要求错误路径必须落在预期类型上。

---

## BUG-002 `--dry-run` 对 ollama 误报「没有 key」

**现象**：

```
[dry-run] key env = OLLAMA_API_KEY -> （未设置）
⚠ 没有 key，真实调用会失败。
```

但 ollama 根本不校验 key，`resolve()` 里有 `default_key` 兜底，实际能跑。

**根因**：`dry_run()` 只读了 `os.getenv()`，没走 `resolve()` 的 `default_key` 逻辑——**同一套规则在两处各实现了一遍**。

**修复**：`dry_run()` 里补上 `default_key` 判断，并把提示改成「内置占位符（该 provider 不校验）」。

**教训**：校验逻辑一旦重复实现，两处必然漂移。理想做法是让 `dry_run` 直接调 `resolve()`。

---

## BUG-003 部分兼容端点不支持 `response_format` 会 400

**现象**：给 ollama / 某些 OpenAI 兼容端点传 `response_format={"type": "json_object"}` 时返回 400。

**发现**：设计时预判 + 本地 ollama 验证。

**根因**：`response_format` 是 OpenAI 的扩展，兼容层不保证实现。

**修复**：捕获 `BadRequestError` 后去掉该参数重试一次，靠 `_loads()` 的容错（解析代码围栏、截取首尾大括号）兜住 JSON。

**取舍**：多一次请求的代价换取跨 provider 可用性，值得。

---

## BUG-004 缺 key 被报成「失败」而非「跳过」

**现象**：没有 `.env` 时跑 `--live -n 3`：

```
第 1 次调用失败：缺少 DEEPSEEK_API_KEY。...
[✗] 真实调用成功  ← 全部失败
M0 结论：有 27 项未通过
```

看起来像 M0 挂了，实际只是没配密钥。

**根因**：把「前置条件缺失」和「系统故障」混为一谈；`section_live` 没有 pre-flight 检查。

**修复**：新增 `[–]` 跳过态与 `check_skip()`；`section_live` 先 `resolve()` 探测，缺 key 直接跳过；退出码细分为 `0 全过 / 1 有失败 / 2 结构过但缺 key`。

**教训**：验收工具的三态（通过/失败/跳过）比两态更贴近现实，尤其在有外部依赖时。

---

## BUG-005 多行错误被截断成半句话

**现象**：

```
第 1 次调用失败：缺少 DEEPSEEK_API_KEY。
  cp .env.example .env   # 然后填入你的 key
（.env 已在 .gitignore 里
```

最后一行断在括号中间，因为 `str(exc)[:80]` 是按字符截断的，把多行错误切了一半。

**修复**：`" ".join(str(exc).split())` 先把换行压成空格，再截断到 120 字符。

**教训**：截断用户可见文本前，先规范化空白，否则切在句子中间比不截断更糟。

---

## BUG-006 统计漏计，显示 `26/28`（本阶段最值得记的一个）

**现象**：

```
通过 26/28（失败 0，跳过 0）
M0 结论：PASS
```

通过 + 失败 + 跳过 ≠ 总数。

**根因**：

```python
check(len(complete) == len(recs) and recs, ...)   # 传进去的是列表，不是 True
...
passed = sum(1 for ok, *_ in results if ok is True)   # 列表 is True → False
```

`A and B` 在 Python 中返回 **B 本身**，不是布尔。`recs` 非空时返回列表，于是这两项既不是 `True` 也不是 `False` 也不是 `None`，三个统计桶全都漏掉：`total` 数到了（28），`passed` 没数到（26）。

**为什么之前看不出来**：打印用的是 `OK if ok else BAD`，列表是真值，所以照常显示 `[✓]`。**显示正常，数字不对**。

**修复**：`check()` 入口加 `ok = bool(ok)`，把类型收干净。

**防复发**：新增 `tests/test_check_m0.py` 五个用例，其中一个直接复现该缺陷（`check(True and [1], ...)` 必须得到 `is True`）。

**教训**：把 `if ok:` 改写成 `if ok is True` 会让判定变严格（这是为了正确区分跳过态的 `None`），但同时要求数据源必须是真布尔——改判定的同时要收数据源类型，否则会出现「显示全对、统计不符」这种最难一眼看出的 bug。

---

## BUG-007 git 身份缺失导致 commit 失败

**现象**：

```
Author identity unknown
fatal: unable to auto-detect email address (got 'ninalym@MacBookPro.(none)')
```

**根因**：从未配置全局 `user.name` / `user.email`；此前的提交是 git 用主机名自动猜的（`ninalym@Ninas-MacBook-Pro.local`）。后来主机名解析变成 `MacBookPro` 且无域，猜测出的邮箱不合法，git 直接拒绝。

**修复（部分）**：在本仓库设置局部身份 `Nina <ninalym13@gmail.com>`。

**待办**：设置全局身份，否则其他项目会重复遇到：

```bash
git config --global user.name "Nina"
git config --global user.email "ninalym13@gmail.com"
```

**教训**：依赖 git 的「自动推断身份」是隐性依赖——它默认能工作，直到主机名或解析环境变了才暴露。

---

## BUG-008 `.DS_Store` 未被忽略

**现象**：`git status` 里出现 `?? .DS_Store`。

**修复**：加入 `.gitignore`。

**教训**：macOS 上用 Finder 浏览过项目就会生成该文件，新仓库初始化时就该忽略。

---

## 本阶段的三类典型模式

1. **异常路径没写**（BUG-001、BUG-004）
   正常路径测试再多也覆盖不到；主动用一个「假 key」「空 `.env`」去跑，问题立刻现形。

2. **隐式类型**（BUG-006）
   `A and B` 返回操作数、`or` 同理、`dict.get()` 返回 `None`——这些在动态类型语言里不会报错，只会在统计或比较时悄悄偏掉。

3. **错误信息截断或指向错误的位置**（BUG-002、BUG-005，以及 troubleshooting 里的 SSH 那条）
   报错说「key 没登记」，实际是本地 agent 没加载；报错切在半句话，反而增加排查时间。**错误信息也是产品的一部分**。

## 写验收脚本时的自查清单

- [ ] 这是「失败」还是「跳过」？前置条件缺失不应该算失败
- [ ] 通过 + 失败 + 跳过 == 总数？打印前先断言一次
- [ ] 传给统计函数的到底是不是布尔值？
- [ ] 用户可见的错误文本是否完整、是否指对了地方？
- [ ] 每个修掉的 bug 是否有对应的回归测试？
