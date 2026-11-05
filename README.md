# 推荐质量 Agent

> 给推荐结果做**可量化**的质量评估：一套可执行的评分标准 + 双模型裁判 + 一致性分析，
> 而不是「看几个 case 拍脑袋」。

![eval](https://github.com/ninalymm/rec-quality-agent/actions/workflows/eval.yml/badge.svg)

**状态**：M0–M4 完成 ｜ M5 门禁已接入 CI ｜ 83 个离线测试 ｜ app 覆盖率 85.8% ｜ Python 3.10+

---

## 它做什么

输入一条请求（用户画像 + 历史行为 + 诉求），Agent 做三件事：

1. **生成** 5 条推荐 —— 从 80 条候选池里挑；标题/类目/日期由代码填，模型只负责选哪 5 条、写理由
2. **算指标** —— 类目覆盖、理由长度、类目分布
3. **打分** —— 4 个维度：时效性、兴趣相关性、内容多样性、理由可解释性

输出：总分（0–8）、逐维得分与证据、每一步的耗时 trace、本次成本。

**它不做什么**：它不是推荐系统本身。这个项目的重点是「怎么判断推荐好不好」，生成只是被评测的对象。

## 看一次真实运行

```console
$ .venv/bin/python -m scripts.run_task --qid Q001

步   工具                 耗时      结果
1    generate_recs      3610ms    5 条推荐
2    metrics_calc        864ms    类目 3 个 / 理由均长 60.6 字
3    score_with_rubric  2284ms    时效1 相关2 多样2 解释1
4    (final)            1096ms    通过，总分 6/8（合格）

结论：5 条推荐覆盖技术、职场、健康 3 个类目，多样性达标；
主要短板是时效性（1 分）和可解释性（1 分），建议补充时效依据、加长推荐理由。
成本 ¥0.0055
```

## 安装

要求 **Python 3.10+**。

```bash
git clone git@github.com:ninalymm/rec-quality-agent.git
cd rec-quality-agent

python3.10 -m venv .venv
.venv/bin/pip install -r requirements.txt          # 国内可加 -i https://pypi.tuna.tsinghua.edu.cn/simple

cp .env.example .env                              # 填 DEEPSEEK_API_KEY 或 DASHSCOPE_API_KEY
```

> clone 必须用 SSH（`git@`）。用 https 在国内会卡在 443，原因见 [troubleshooting](docs/troubleshooting.md)。

## 用法

```bash
# 1. 跑一次完整评测（生成 → 指标 → 打分）
.venv/bin/python -m scripts.run_task --qid Q001

# 2. 起 HTTP 服务
.venv/bin/python -m uvicorn app.main:app --port 8000
curl -X POST localhost:8000/task -H "Content-Type: application/json" -d '{"qid":"Q001"}'
curl localhost:8000/task/1        # 按 task_id 回放完整 trace

# 3. 评测**已经生成好**的推荐（不重新生成，只打分）
.venv/bin/python -m scripts.eval_recs --input data/recs_v1.jsonl --limit 20

# 4. 只验证生成链路（不评测，适合排查配置）
.venv/bin/python -m scripts.smoke_recs

# 5. 测试（全部离线，不需要 key；覆盖率门槛在 CI 里卡，本地只显示）
.venv/bin/python -m pytest
```

Docker：

```bash
docker compose up -d --build      # 起服务；国内拉不到基础镜像时见 docs/troubleshooting.md
```

`run_task` 是「生成 + 评测」；如果你的推荐来自别处（线上系统、人工构造、历史落盘），
用 `eval_recs` 直接喂 JSONL 评测，不触发生成：

```json
{"qid": "Q001", "recommendations": [{"title": "...", "category": "技术", "published_at": "2026-10-20", "reason": "..."}]}
```

跑完的任务存在 `data/tasks.db`，用 `python -m scripts.inspect_db` 或任意 SQLite 工具查看，
常用查询见 [docs/sql-queries.md](docs/sql-queries.md)。

## 架构

四层，依赖单向向下：

```
scripts/            入口：CLI 脚本（run_task / smoke_recs / inspect_db）
      ↓
app/agent.py        Agent 循环：模型决定调哪个工具，代码执行并维护状态
      ↓
app/recs.py         业务：generate_recs() 生成推荐
app/llm.py          能力：provider 工厂（deepseek / qwen / ollama）+ 成本估算
app/prompts.py      能力：prompt 模板
      ↓
app/config.py       配置：全项目唯一的 os.getenv 出口
```

三个工具构成固定依赖链：`generate_recs → metrics_calc → score_with_rubric`。
工具参数只传 `qid`，其余数据从内存 state 取——模型擅长判断，不擅长搬运。

## 评测结果

| 指标 | 结果 |
|---|---|
| 客观维度一致性（3 个维度，代码计算） | kappa **1.000**（设计使然，可作流程自检） |
| 语义维度 judge↔judge | kappa **0.485 ± 0.05** |
| 语义维度 judge↔人工 | kappa **0.300**（51 条盲标） |
| 位置偏差（5 条顺序反转） | DeepSeek **2.0%** ／ Qwen **12.0%** |
| 单条评测成本 | **¥0.009**（一次生成 + 两次判定） |

**核心结论：judge 可以粗筛，不能判不合格。** 它比人宽 25 次、比人严 0 次——
人判 2 分的 8 条它全对，人判 0/1 分的它经常给高分。

完整报告与失败分析见 [eval/REPORT.md](eval/REPORT.md)。

## 设计取舍

| 决定 | 理由 |
|---|---|
| 能代码算的维度不交给模型 | 日期差、类目命中、类型数都是确定性计算，交给 LLM 只会引入方差 |
| 用候选池代替自由生成 | 否则模型编的 `published_at` 会让时效性维度失效——测到的成了「编日期的水平」 |
| 模型只输出 `{id, reason}` | 标题/类目/日期由代码从池子里填，输出里四个字段有三个不可能出错 |
| 注入 30 条降级样本做人工标注 | 原始推荐几乎条条合格，不注入坏样本，可解释性维度没有区分度 |

## 已知局限

- **数据是合成的**：候选池 80 条内容由人写，不是真实内容平台的数据，分布偏理想
- **judge 单向偏宽**（见上）：kappa 0.300 低于 0.4 的常用门槛
- **judge 有随机性**：同一判定标准重跑两次，kappa 差 0.045，所以报告写成「约 0.49 ± 0.05」
- **位置敏感度因模型而异**：Qwen 12% 的样本会因顺序改变而改判，用 Qwen 当裁判需固定顺序

## 里程碑

- [x] **M0** 环境与数据：跑通一次 LLM 调用
- [x] **M1** 评测集：4 维度 rubric + 200 条 query + 200 组检查点
- [x] **M2** 双 judge：kappa / 位置偏差 / 成本三个数字
- [x] **M3** Agent 骨架：规划 → 工具 → 产出循环
- [x] **M4** 工程化：结构化日志 + 超时重试 + Docker + 85.8% 覆盖率（已在新环境复现通过）
- [x] **M5** CI 回归门禁：20 条回归集 + 两关 CI（[红→绿记录](docs/ci-evidence.md)）
- [ ] **M6** 材料：demo 视频 + 10 分钟讲稿 + 失败案例

每个里程碑的目标、产出、验收标准与证据位置，见 [docs/milestones.md](docs/milestones.md)。

## 文档

| 文档 | 内容 |
|---|---|
| [docs/milestones.md](docs/milestones.md) | M0–M6 的目标、产出、验收标准与证据 |
| [eval/rubric.md](eval/rubric.md) | 评分标准：4 个维度、锚点、反例、聚合规则 |
| [eval/REPORT.md](eval/REPORT.md) | 评测报告：kappa、位置偏差、成本、结论与局限 |
| [docs/rubric-review.md](docs/rubric-review.md) | 评分标准设计过程中的 17 个问题与 6 类根因 |
| [docs/bugs.md](docs/bugs.md) | 17 个代码/文档缺陷的定位与修复过程 |
| [docs/troubleshooting.md](docs/troubleshooting.md) | 环境、网络、解释器的坑（443 阻断、SSH、Rosetta） |
| [docs/sql-queries.md](docs/sql-queries.md) | 任务库的常用 SQL（含用 `json_each` 统计工具耗时） |

## License

MIT © 2026 Nina
