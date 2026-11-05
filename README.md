# 推荐质量 Agent（Rec-Quality Agent）

> 给一个用户请求 → 生成推荐 → 按 rubric 多维打分 → 输出质量问题与改进建议，每次改动都过 CI 回归校验。

**状态**：M0 完成 ✅ · M1 完成 ✅ · M2 进行中 🚧 · Python 3.10+ · MIT

---

## 它解决什么问题

推荐系统的效果评估长期靠「看几个 case 拍脑袋」：改了一版 prompt 或策略，没人说得清是变好还是变坏，更说不清好多少。

这个项目把评估变成可执行的东西：**评分标准（rubric）+ 双模型裁判（judge）+ 人工标注对账（kappa）+ CI 回归门禁**。

目标不是做一个推荐系统，而是给推荐系统装一套能持续跑的质检流水线。

## 现在做到哪了

M0（环境与数据）已完成：一次 LLM 调用能生成 5 条带理由的推荐，并被自动验收。

| 指标 | 实测值 | 怎么来的 |
|---|---|---|
| 验收检查 | **31/31 通过** | `python -m scripts.check_m0 --live` |
| 离线单测 | **22 passed** | 不联网、不需要 key，CI 可跑 |
| 单次调用成本 | **¥0.0028** | prompt 200 + completion 303 tokens |
| 推荐条数 | 5/5，字段齐全 | 结构合规检查 |
| 类目多样性 | 3 类（技术深度 / 职场 / 跑步） | 同一 batch 内去重计数 |
| 理由可解释性 | 平均 40.2 字，5/5 引用用户画像或历史 | 启发式匹配 |
| 支持模型 | DeepSeek（默认）/ Qwen / 本地 Ollama | `--provider` 一行切换 |

以上数字均可复现，不是估计值。

### M1：评测集（已完成）

| 产出 | 规模 | 位置 |
|---|---|---|
| 评分标准 | 4 维度 + 聚合规则 | [`eval/rubric.md`](eval/rubric.md) |
| 评测 query | **200 条**（180 常规 + 20 边界） | [`data/queries.csv`](data/queries.csv) |
| 理想答案要点 | **200 组**，每组 3–4 条 | [`data/checklists.jsonl`](data/checklists.jsonl) |
| 候选池 | **80 条**，8 类目 × 10 | [`data/candidates/pool_v1.csv`](data/candidates/pool_v1.csv) |
| 生成器 | 可复现（固定随机种子） | [`scripts/gen_queries.py`](scripts/gen_queries.py) |

三个设计取舍：

1. **3 个客观维度 + 1 个语义维度**。日期、类目命中、类型数都能用代码算，交给模型只会引入方差；
   只有「理由是否引用了具体历史」必须靠 judge 判断。
2. **用候选池代替自由生成**。让模型自己编标题，`published_at` 也会是编的，时效性维度就失效了——
   测到的成了「模型编日期的水平」。候选池让模型只能从给定条目里挑，日期由代码填充。
3. **20 条边界案例**。无历史、单类目、兴趣冲突、条数限制、否定约束——正常用户不会这么问，
   但 judge 最容易在这些地方出错，也是 M5 回归集的来源。

设计过程中的 16 个问题与 6 类根因，记录在 [`docs/rubric-review.md`](docs/rubric-review.md)。

## 快速开始

要求 **Python 3.10+，原生 arm64**。Apple Silicon 上用 Rosetta 的 x86 解释器会导致 pandas 加载失败（原因见 [troubleshooting](docs/troubleshooting.md) 第 4 条）。

```bash
git clone git@github.com:ninalymm/rec-quality-agent.git
cd rec-quality-agent

/usr/local/bin/python3.10 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env      # 填入 DeepSeek 或 Qwen 的 key（.env 已被 .gitignore 排除）
```

跑起来：

```bash
.venv/bin/python -m pytest                          # 22 个离线单测（不需要 key）
.venv/bin/python -m scripts.smoke_recs --dry-run    # 只检查配置与 prompt，不花钱
.venv/bin/python -m scripts.smoke_recs              # 真实调用：生成 5 条推荐
.venv/bin/python -m scripts.check_m0 --live         # 完整验收（31 项）
```

没有 API key 也能验证链路：

```bash
ollama serve                # 另开一个终端跑；或后台 ollama serve &
ollama pull qwen2.5:7b
.venv/bin/python -m scripts.smoke_recs --provider ollama
```

7B 模型出结构化 JSON 不稳定，只适合验链路，不适合跑评测。

## 架构

四层，依赖单向向下：

```
scripts/           入口层   命令行脚本，只负责参数解析与输出
      ↓
app/recs.py        业务层   generate_recs()：编排调用、解析结果、计算成本
      ↓
app/llm.py         能力层   provider 工厂（deepseek/qwen/ollama）+ 成本估算
app/prompts.py     能力层   prompt 模板，与代码分离
      ↓
app/config.py      配置层   全项目唯一的 os.getenv 出口
```

为什么这么分：

- **`config.py` 收口配置**：业务代码里看不到环境变量和魔法数字，换超时、换默认模型只改一处
- **`prompts.py` 独立**：M1 要反复加评分维度、M2 要做 A/B 顺序实验，prompt 必须能被单独 diff
- **`llm.py` 不掺业务**：只负责建 client 和算钱；M2 的「双 judge」靠它一行切换 provider
- **`recs.py` 是唯一的业务语义层**：也是 M3 里 `generate_recs` 这个工具的雏形

## 评测结果

M2 完成后填入。计划记录三个数字：

| 指标 | 当前结果 | 状态 |
|---|---|---|
| judge ↔ judge 一致性 | 客观维度 **1.000**；可解释性 **0.530**（v2 判定标准） | ✅ 已完成（[REPORT.md](eval/REPORT.md)） |
| 位置偏差 | 顺序反转后 DeepSeek **2.0%** / Qwen **12.0%** | ✅ 已完成（各 50 条） |
| 评测成本 | 单条 **¥0.009**，200 条全量 **¥1.73** | ✅ 已实测 |
| judge ↔ 人工 kappa | DeepSeek **0.300** / Qwen 0.238（51 条） | ✅ 已完成，判定单向偏宽 |

## Roadmap

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 环境与数据：跑通一次 LLM 调用 | ✅ 完成 |
| M1 | 评测集：200 条 query + rubric | ✅ 完成 |
| M2 | 双 judge + 一致性分析（kappa / 偏差 / 成本） | 🚧 进行中 |
| M3 | Agent 骨架：规划 → 工具 → 产出循环 | ⬜ |
| M4 | 工程化：Docker + 结构化日志 + 测试覆盖 | ⬜ |
| M5 | CI 回归门禁（红 → 绿截图） | ⬜ |
| M6 | 材料：3 分钟 demo + 讲稿 + 失败案例 | ⬜ |

## 开发

```bash
.venv/bin/python -m pytest            # 22 个离线单测
.venv/bin/python -m scripts.check_m0  # 结构层验收（24 项，不花钱）
```

约定：

- 配置只进 `app/config.py`，prompt 只进 `app/prompts.py`
- 单测必须离线可跑（不联网、不需要 key），否则 CI 不稳定
- commit 前缀：`feat(scope):` / `fix(scope):` / `docs(scope):` / `test(scope):`
- **发现问题必须存档**：代码/文档缺陷进 [docs/bugs.md](docs/bugs.md)，环境/网络/工具链进 [troubleshooting.md](docs/troubleshooting.md)。五要素（现象/发现/根因/修复/防复发）缺一不可，且与修复放在同一个 commit 里。规则详见 [docs/README.md](docs/README.md)

踩坑记录（都是真实踩过的，附诊断命令）：

- [docs/troubleshooting.md](docs/troubleshooting.md) — 环境 / 网络 / 解释器：443 概率性阻断、SSH 口令未加载、GitHub 停用密码认证、pandas 架构不匹配
- [docs/bugs.md](docs/bugs.md) — M0 阶段 8 个代码缺陷，含「显示正常但统计不对」这类隐蔽问题的定位过程

## 目录结构

<details>
<summary>展开查看</summary>

```
rec-quality-agent/
├── app/                      应用代码
│   ├── config.py             配置：路径、provider、超时、条数
│   ├── prompts.py            prompt 模板
│   ├── llm.py                provider 工厂 + 成本估算
│   ├── recs.py               generate_recs() 业务逻辑
│   ├── agent.py              M3：规划-工具-产出循环
│   ├── main.py               M3：FastAPI 入口
│   ├── store.py              M3：SQLite 任务与轨迹
│   ├── logging.py            M4：结构化日志
│   └── tools/                M3：metrics.py / sql_query.py
├── scripts/
│   ├── smoke_recs.py         最小链路验证：生成 5 条推荐
│   └── check_m0.py           M0 验收：31 项检查
├── tests/                    离线单测（22 个）
├── data/                     queries.csv / labels.csv（M1/M2 填充）
├── eval/                     rubric.md / judge.py / agreement.py / REPORT.md
├── docs/                     README（索引与规则）/ troubleshooting.md / bugs.md
├── .github/workflows/        M5：CI 回归门禁
├── pytest.ini                测试路径与导入路径
└── requirements.txt
```

</details>

## License

MIT © 2026 Nina
