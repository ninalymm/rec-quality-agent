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
| BUG-007 | git 身份缺失导致 commit 失败 | 中 | commit 时报错 | 已修 |
| BUG-008 | `.DS_Store` 未被忽略 | 低 | `git status` | 已修 |
| BUG-009 | README 里的 shell 命令语法错误 | 中 | 复查文档 | 已修 |
| BUG-010 | 分析脚本用 zip 对齐并发写出的文件 | 中 | 对比数字对不上 | 已修 |
| BUG-011 | 调度器传两参、handler 只收一参 | 高 | 跑任务时报 TypeError | 已修 |
| BUG-012 | requirements 缺 pytest-cov，新环境 pytest 直接失败 | 高 | 通读 README 时发现 | 已修 |
| BUG-013 | `cp .env.example .env` 会清空已填的 key | 高 | 用户反馈时顺带发现 | 已修 |
| BUG-014 | 移除 pandas 后 check_m0 仍要求它 | 高 | 干净环境跑验收 | 已修 |
| BUG-015 | README 克隆命令重复执行产生嵌套目录 | 中 | 陌生人复现时踩到 | 已修 |
| BUG-016 | dry-run 截断 prompt 却不说明，像只有 6 条候选 | 中 | 用户误判候选池大小 | 已修 |
| BUG-017 | 快速开始难读：无目标、无分步、无成功标志 | 中 | 用户反馈 | 已修 |

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

**修复**：两级都配了。

```bash
# 仓库级（先做，解当时之急）
git config user.name "Nina"
git config user.email "ninalym13@gmail.com"

# 全局级（根治，覆盖其他项目）
git config --global user.name "Nina"
git config --global user.email "ninalym13@gmail.com"
```

**验证**：`git config --list --show-origin | grep user` 显示来自 `~/.gitconfig`；再在工作区外的空目录做一次 `git commit --allow-empty`，作者为 `Nina <ninalym13@gmail.com>`，确认全局配置真的生效（而不是只在某个仓库里对）。

**注意**：改身份只影响**之后的**提交，历史 commit 的作者不变——本项目早期几个提交仍是 `ninalym@Ninas-MacBook-Pro.local`。要改历史得 `git filter-branch` / `git rebase -i` 重写，公开仓库上还会引发强推，没必要。

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

---

## BUG-009 README 里的 shell 命令语法错误

**现象**：

```bash
ollama serve & && ollama pull qwen2.5:7b
# bash: syntax error near unexpected token `&&'
```

读者按 README 复制执行，第一条命令就报错。

**发现**：写完 README 五分钟后自查发现（不是读者反馈）。

**根因**：把两个意图混在一行——「后台运行 `ollama serve`」和「顺序执行 `ollama pull`」。`&` 本身已经结束了一条命令，后面不能再接 `&&`。

**修复**：拆成两行并加注释：

```bash
ollama serve                # 另开一个终端跑；或后台 ollama serve &
ollama pull qwen2.5:7b
.venv/bin/python -m scripts.smoke_recs --provider ollama
```

**防复发**：`check_m0` 新增 `section_docs()`，把 README 里所有 ```bash 代码块抽出来，用 `bash -n` 做**语法解析**（只解析、不执行，安全）。命令写错的 README 现在会让验收直接失败。

**教训**：README 里的命令是最先被读者执行的部分，也是唯一不会被测代码覆盖的部分。写文档时的「顺手一改」特别容易留下语法错误，必须机器校验——人眼看得再仔细也扫不出来。

---

## BUG-010 分析脚本用 zip 对齐两份判定结果

**现象**：临时脚本里想比较 DeepSeek 与 Qwen 的可解释性分数，写成：

```python
for a, b in zip(ds, qw):   # 两个 list 按位置对齐
```

算出来一致率 81.0%，而已提交的 `eval/agreement.py` 算出 87.0%。

**根因**：两份判定文件都是**多线程并发写入**的，行序是完成顺序，不是 qid 顺序。
按位置 zip 会把 Q001 的判定和 Q037 的判定配成一对。

**修复**：按 `qid` 建字典再配对：

```python
ds = {r["qid"]: r for r in ...}
common = sorted(set(ds) & set(qw))
```

**防复发**：`eval/agreement.py` 一开始就是按 qid 对齐的，所以提交的代码没受影响——
问题只出在临时的对比脚本上。结论：**并发写出的文件，任何跨文件对齐都必须用 id，不能用行号**。

**教训**：这类错误不会报错，只会让数字悄悄偏掉；而偏掉的数字如果先写进报告，很难再发现。

---

## BUG-011 调度器传两参、handler 只收一参

**现象**：重构为声明式调度后跑 Q007，模型连续两次调用 `generate_recs` 都拿到：

```
TypeError: _tool_generate() takes 1 positional argument but 2 were given
```

**有意思的地方**：Agent 自己把这个错误诊断出来了——

> `generate_recs` 连续两次返回同一个内部错误……说明该工具的实现存在参数签名 bug
> （把 qid 当作第二个位置参数传入），并非偶发失败。

它甚至建议「修复参数绑定后重跑」。但这恰恰说明**不能靠模型兜底来掩盖代码 bug**：
模型花了两轮、多花 ¥0.002 才绕过去，而正确做法是一次跑通。

**根因**：`dispatch` 调用约定是 `handler(state, args)`，但三个 handler 写成了单参数。
单元测试没覆盖到——测试里用 stub 替换了 handler，反而绕开了签名检查。

**修复**：三个 handler 统一改为 `(state, args=None)`。

**防复发**：新增 `test_provides_covers_requirements`（检查依赖图无断头），
但**没有**测试 handler 签名——这是缺陷。补法：加一条测试，遍历 `TOOL_SPECS`
用假 state/args 调用每个 handler，断言不会抛 `TypeError`。

**教训**：用 stub 替换被测对象时，会同时绕开它与调度器之间的契约检查。
契约类缺陷（参数个数、返回结构）必须有单独的测试，不能只测业务逻辑。

---

## BUG-012 requirements 缺 pytest-cov，新环境跑 pytest 直接失败

**现象**：`pytest.ini` 里有 `addopts = --cov=app --cov-fail-under=60`，
但 `requirements.txt` 只写了 `pytest`，没写 `pytest-cov`。

新机器照 README 装完依赖后跑 `pytest`：

```
ERROR: usage: pytest [options] [file_or_dir] [...]
pytest: error: unrecognized arguments: --cov=app --cov-report=term-missing --cov-fail-under=60
```

**发现方式**：准备做「陌生人复现」验收时，**先照着 README 通读了一遍**，
看到 pytest 那一行才想到「这个 --cov 是谁提供的」。

**为什么本机没暴露**：`pytest-cov` 是我中途手动 `pip install` 的，
没回写进 requirements——本机永远跑得通，新环境必挂。

**修复**：requirements 补 `pytest-cov==7.1.0`。

**顺带发现**：`pandas` 也在 requirements 里，但全项目**没有任何代码 import 它**
（M1 处理 CSV 时用的是标准库 `csv`）。它还是「Rosetta 下轮子被拒载」那个坑的源头。

**处理**：移除 pandas。README 里「必须原生 arm64」的说明相应改成「需要 Python 3.10+」。

**教训**：依赖清单最容易出现「本机能跑、新环境挂」的隐性缺陷——因为开发过程中
随手 `pip install` 的东西，没人会记得回填。**唯一可靠的检验是换一个干净环境装一遍**，
这也正是 M4 那条「陌生人 10 分钟跑起来」验收的价值。

---

## BUG-013 README 的 `cp .env.example .env` 会清空已填的 key

**现象**：快速开始里写的是

```bash
cp .env.example .env      # 填入 key
```

第一次执行没问题。但**第二次执行时**（比如换机器重跑、或忘了自己已经配过），
`cp` 会直接用模板覆盖 `.env`，**已填的 API key 被清空**。

**发现方式**：用户反馈「`cp` 之后还要自己找文件去填 key，能不能直接打开」——
改这条命令时意识到，`cp` 本身还有个覆盖问题。

**为什么危险**：`.env` 在 `.gitignore` 里，被清空后**没有任何版本记录可以恢复**，
只能重新去平台生成 key。

**修复**：

```bash
[ -f .env ] || cp .env.example .env     # 已存在就跳过
open -e .env                            # 直接打开编辑
```

**验证**：先在临时目录造一个含 key 的 `.env`，再执行该命令，key 行保持不变。

**教训**：文档里的「初始化」命令应该默认**幂等**——用户可能在任何时候重跑，
而不是只在干净环境跑一次。所有 `cp` / `mv` / `rm` 出现在快速开始里时，都要问一句
「第二次跑会发生什么」。

---

## BUG-014 移除 pandas 后，check_m0 仍把它当必需依赖

**现象**：在新环境跑 M0 验收，第一条就红：

```
[✗] 依赖可导入: pandas  ← No module named 'pandas'
```

但 `pandas` 是当天刚被从 `requirements.txt` 移除的（BUG-012 的连带改动，全项目无 import）。

**根因**：`scripts/check_m0.py` 里硬写了一份依赖清单，与 `requirements.txt` 是**两份独立的真相**。
删依赖时只改了 requirements，没同步验收脚本。

**为什么本机没暴露**：旧 venv 里 pandas 还装着（当初 pip install 的残留），
所以 `__import__("pandas")` 一路绿灯。**只有干净环境才会红。**

**修复**：从 check_m0 的清单里移除 pandas，并注明与 requirements 同步。

**防复发**：依赖清单不该在两处各写一份。更好的做法是让 check_m0 读 `requirements.txt` 解析包名，
而不是维护一个手写列表——这样删依赖只需改一处。

**教训**：同一事实存在两个副本时，改一处必然漏另一处。
这次是「依赖清单」，下次可能是「默认端口」「支持的模型列表」。

---

## BUG-015 README 的克隆命令重复执行会产生嵌套目录

**现象**：在已有仓库的目录里再次执行快速开始的第一段，会克隆出套娃结构：

```
/tmp/recqa-fresh/                                 第 1 次 clone
/tmp/recqa-fresh/rec-quality-agent/               第 2 次
/tmp/recqa-fresh/rec-quality-agent/rec-quality-agent/   第 3 次
```

`.env` 被建在最里层，而从外层运行命令时读不到它 → 表现成「配置明明填了却报缺 key」。

**发现方式**：用户做「陌生人复现」时踩到，报错信息是 `key 无效`，
但排查发现 `.env` 在第三层目录里。

**根因**：README 的 `git clone ... && cd rec-quality-agent` 是**不可重入**的。
它假设读者在空目录，但「复现时反复执行同一段命令」是很自然的操作。

**修复**：克隆那段拆成两步并加提示——

```
# ① 克隆（在空目录执行；如果当前目录已经是本仓库根目录，跳过这两行）
```

**教训**：快速开始里的每一步都该问「第二次执行会发生什么」。
这已经是同类问题的第三次（BUG-012 依赖、BUG-013 覆盖 .env、本条套娃）——
**初始化脚本/文档天然应该幂等**。

---

## BUG-016 dry-run 截断 prompt 却不说明，看起来像候选池只有 6 条

**现象**：跑 `smoke_recs --dry-run`，输出里只看到 6 行候选：

```
C001 | 技术 | 2026-10-31 | Go 1.24 调度器有哪些变化
...
C006 | 技术 | 2026-09-15 | 微服务拆分的边界怎么定 ...
```

用户据此判断「候选池只有 6 个」。

**实际情况**：候选池 80 条，完整 prompt 3374 字符、80 行候选。
`dry_run` 里写的是 `print(messages[1]["content"][:400] + " ...")`——只打印前 400 字符。

**根因**：截断本身是合理的（dry-run 不该刷 3000+ 字符），
但**没有告诉读者「这里是截断的」**，于是「没显示」被误读成「没有」。

**修复**：输出里带上实际数量——

```
[dry-run] prompt 共 2 条消息，3374 字符；候选 80 条（下面只显示前 400 字符）
```

**教训**：任何截断/采样/省略的展示，都必须同时给出「总量」。
只给部分而不给总数，等于让读者用局部推断整体——这不是读者的错。

---

## BUG-017 快速开始难读：没有目标、没有分步、没有成功标志

**现象**：用户反馈——

> 在读 README 的时候快速开始是需要干什么，很难理解。另外方式二又是什么意思，文本阅读起来困难。

具体有五个问题：

| # | 问题 |
|---|---|
| 1 | 开头直接是 `git clone`，**没说做完能得到什么** |
| 2 | 一个代码块塞了克隆/建 venv/装依赖/填 key 四件事，只能整段复制 |
| 3 | 出现「方式二：Docker」却**没有「方式一」**，读者会往回找 |
| 4 | 说 Docker「一条命令」，实际是 4 条命令 + 一次构建 |
| 5 | 每一步都**没有「成功标志」**，跑完不知道对不对 |

**根因**：按「我知道的步骤顺序」写，而不是按「读者需要确认什么」写。
作者视角是「命令清单」，读者视角是「我做到哪了、现在对不对」。

**修复**：整节重写为「目标 → 四步表格 → 每步：命令 + 成功标志」，
Docker 提升为独立的一节「另一种方式：Docker」，并注明什么时候用它。

**教训**：**快速开始的每一节都该能回答「我现在在哪、怎么知道成功了」。**
命令清单只解决了「怎么做」，解决不了「我做对了吗」——而后者才是新手卡住的地方。
