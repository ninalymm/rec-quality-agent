# 推荐质量 Agent（Rec-Quality Agent）

> 给一个用户请求 → 生成推荐 → 按 rubric 多维打分 → 输出质量问题与改进建议，每次改动都过 CI 回归校验。

**状态**：M0–M3 完成 ✅ · Python 3.10+ · MIT

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

要求 **Python 3.10+**（代码用了 `X | None` 语法）。不需要 pandas，也不再受"Rosetta 下 x86 wheel 被拒载"的影响。

```bash
git clone git@github.com:ninalymm/rec-quality-agent.git
cd rec-quality-agent

/usr/local/bin/python3.10 -m venv .venv
.venv/bin/pip install -r requirements.txt        # 国内可加：-i https://pypi.tuna.tsinghua.edu.cn/simple

cp .env.example .env      # 填入 DeepSeek 或 Qwen 的 key（.env 已被 .gitignore 排除）
```

> clone 用 SSH 地址（`git@`）。用 https 在国内会卡在 443，原因见 [troubleshooting](docs/troubleshooting.md) 第 1 条。

跑起来：

```bash
.venv/bin/python -m pytest                          # 81 个离线单测（不需要 key）
.venv/bin/python -m scripts.smoke_recs --dry-run    # 只检查配置与 prompt，不花钱
.venv/bin/python -m scripts.smoke_recs              # 真实调用：生成 5 条推荐
.venv/bin/python -m scripts.check_m0 --live         # 完整验收（31 项）
```

### 方式二：Docker（一条命令）

```bash
cp .env.example .env      # 填 key
docker compose up -d --build
curl localhost:8000/health
curl -X POST localhost:8000/task -H "Content-Type: application/json" -d '{"qid":"Q001"}'
curl localhost:8000/task/1
```

国内网络拉不到 `python:3.10-slim` 时，用镜像源覆盖：

```bash
docker build \
  --build-arg BASE_IMAGE=docker.m.daocloud.io/library/python:3.10-slim \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  -t rec-quality-agent:0.1 .
docker compose up -d --no-build
```

没有 API key 也能验证链路：

```bash
ollama serve                # 另开一个终端跑；或后台 ollama serve &
ollama pull qwen2.5:7b
.venv/bin/python -m scripts.smoke_recs --provider ollama
```

7B 模型出结构化 JSON 不稳定，只适合验链路，不适合跑评测。

## 跑完之后：怎么看结果

每次任务会写一行到 `data/tasks.db`（本地）或 `data/tasks-container.db`（容器），
包含结论、完整轨迹、耗时与成本。三种查看方式：

```bash
# ① 命令行（不装任何东西）
python -m scripts.inspect_db                 # 最近 10 条
python -m scripts.inspect_db --trace 9       # 某条的完整轨迹
python -m scripts.inspect_db --db data/tasks-container.db

# ② sqlite3（系统自带）
sqlite3 -header -column data/tasks.db \
  "SELECT id,qid,status,steps,round(cost_cny,5) FROM tasks ORDER BY id DESC LIMIT 5;"

# ③ GUI：DBeaver / TablePlus 新建 SQLite 连接，选 data/tasks.db
```

`inspect_db --trace` 的输出：

```
任务 9 | qid=Q030 | status=done | steps=4 | ¥0.00504 | 839d38434ee3
步   工具                 耗时      结果
1    generate_recs       3236ms    {"count": 5, "titles": [...]}
2    metrics_calc        848ms     {"count": 5, "types": 3, ...}
3    score_with_rubric   2189ms    {"dims": {...}}
4    (final)             1057ms    **Q030 评测结论…**
```

轨迹存成 JSON 字段，用 SQLite 的 `json_each` 可以拆开做聚合——比如统计各工具的平均耗时：

```sql
SELECT json_extract(t.value,'$.tool') AS tool,
       ROUND(AVG(json_extract(t.value,'$.latency_ms'))) AS avg_ms
FROM tasks, json_each(tasks.trace) t
GROUP BY tool ORDER BY avg_ms DESC;
```

完整的查询清单见 [docs/sql-queries.md](docs/sql-queries.md)（总览 / 成本 / 性能 / 失败分析 / 导出）。

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
| judge ↔ judge 一致性 | 客观维度 **1.000**；可解释性 **0.485**（v2，重跑波动 ±0.05） | ✅ 已完成（[REPORT.md](eval/REPORT.md)） |
| 位置偏差 | 顺序反转后 DeepSeek **2.0%** / Qwen **12.0%** | ✅ 已完成（各 50 条） |
| 评测成本 | 单条 **¥0.009**，200 条全量 **¥1.73** | ✅ 已实测 |
| judge ↔ 人工 kappa | DeepSeek **0.300** / Qwen 0.238（51 条） | ✅ 已完成，判定单向偏宽 |

## Roadmap

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 环境与数据：跑通一次 LLM 调用 | ✅ 完成 |
| M1 | 评测集：200 条 query + rubric | ✅ 完成 |
| M2 | 双 judge + 一致性分析（kappa / 偏差 / 成本） | ✅ 完成 |
| M3 | Agent 骨架：规划 → 工具 → 产出循环 | ✅ 完成 |
| M4 | 工程化：Docker + 结构化日志 + 测试覆盖 | ✅ 完成 |
| M5 | CI 回归门禁（红 → 绿截图） | 🚧 进行中 |
| M6 | 材料：3 分钟 demo + 讲稿 + 失败案例 | ⬜ |

## 数据与日志的位置

| 运行方式 | 任务数据库 | 日志 |
|---|---|---|
| 本地 | `data/tasks.db` | 终端 stderr（一行 JSON） |
| Docker | `data/tasks-container.db`（compose 里用 `TASKS_DB` 指定） | `docker compose logs` |

两者独立，互不污染。想改路径就设环境变量：

```bash
TASKS_DB=/tmp/my.db python -m scripts.run_task --qid Q001
```

## 开发

```bash
.venv/bin/python -m pytest            # 81 个离线单测，覆盖率低于 60% 会失败
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
│   ├── logging.py            M4：结构化日志（一行 JSON，trace_id 自动注入）
│   ├── resilience.py         M4：分级超时 / 重试 / 降级
│   └── tools/                M3：metrics.py / sql_query.py
├── scripts/
│   ├── smoke_recs.py         最小链路验证：生成 5 条推荐
│   ├── run_task.py           跑一次 Agent 任务并打印 trace
│   ├── inspect_db.py         查看任务库与轨迹
│   ├── gen_queries.py        生成 200 条评测 query（固定种子可复现）
│   ├── gen_checklists.py     生成 200 组理想答案要点
│   └── check_m0.py           M0 验收：24 项结构检查
├── tests/                    81 个离线单测（不联网、不需要 key）
├── data/                     queries.csv / labels.csv（M1/M2 填充）
├── eval/                     rubric.md / judge.py / agreement.py / REPORT.md
├── docs/                     troubleshooting / bugs / rubric-review / sql-queries
├── .github/workflows/        M5：CI 回归门禁
├── pytest.ini                测试路径与导入路径
└── requirements.txt
```

</details>

## License

MIT © 2026 Nina
