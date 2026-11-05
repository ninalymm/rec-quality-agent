# 里程碑 M0–M6

> 计划来源：6 周 120h 的个人项目计划。每个阶段都有明确的「产出」和「验收标准」，
> 验收不通过不进下一阶段。

## 总表

| 里程碑 | 目标 | 产出 | 验收标准 | 状态 |
|---|---|---|---|---|
| **M0** 环境与数据 | 跑通一次 LLM 调用 | repo 骨架、provider 工厂、验收脚本 | 验收脚本全绿（23 项结构检查） | ✅ |
| **M1** 评测集 | 200 条 query + 评分标准 | `queries.csv`、`rubric.md`、`checklists.jsonl` | 陌生人能照 rubric 打分（已做 51 条人工试标） | ✅ |
| **M2** 双 judge | 三个数字：kappa / 位置偏差 / 成本 | `judge.py`、`agreement.py`、`REPORT.md` | 三个数字都有，且能解释怎么算的 | ✅ |
| **M3** Agent 骨架 | 规划 → 工具 → 产出循环 | `agent.py`、`main.py`、`store.py` | `curl` 能拿到结果，trace 能看到每步输入输出与耗时 | ✅ |
| **M4** 工程化 | 别人 10 分钟能跑起来 | 结构化日志、超时重试降级、Docker、83 个测试 | 新环境照 README 跑通一次（已由第二方复现） | ✅ |
| **M5** CI 门禁 | 改坏 prompt 能被 CI 拦住 | `.github/workflows/eval.yml`、20 条回归集 | CI 上有一次真实的红→绿记录（待配 secret 后演示） | 🚧 |
| **M6** 材料 | 能对着人讲 10 分钟 | demo 视频、讲稿、3 个失败案例 | 讲完不卡壳 | ⬜ |

## 证据在哪

| 里程碑 | 可以直接指给人看的东西 |
|---|---|
| M0 | `python -m scripts.check_m0` 的输出；[tests/](../tests/) 81 个离线用例 |
| M1 | [data/queries.csv](../data/queries.csv) 200 条 ｜ [eval/rubric.md](../eval/rubric.md) 4 维度 ｜ [data/checklists.jsonl](../data/checklists.jsonl) 200 组 |
| M2 | [eval/REPORT.md](../eval/REPORT.md)：judge↔judge kappa 0.485、judge↔人工 0.300、位置偏差 2%/12%、单条 ¥0.009 |
| M3 | `python -m scripts.run_task --qid Q001` 的四步 trace；`data/tasks.db` 可回放 |
| M4 | [Dockerfile](../Dockerfile) + `docker compose up`；日志单行 JSON，`trace_id` 可串全链路 ｜ **2026-11-05 在 `/tmp` 全新环境由作者本人复现通过**（非开发环境），过程中发现 6 个缺陷 + 2 处改进 |
| M5 | [data/regression_tasks.json](../data/regression_tasks.json) 20 条 ｜ [eval/regression.py](../eval/regression.py) ｜ [docs/quality-gate.md](quality-gate.md) 记录噪声实测 ｜ CI 已跑通（[run](https://github.com/ninalymm/rec-quality-agent/actions)） |
| M6 | 待建（计划：3 分钟 demo + 10 分钟讲稿 + 3 个失败案例） |

---

## M0 详情：环境与数据

一次 LLM 调用能生成 5 条带理由的推荐，并被自动验收。

| 指标 | 实测值 | 怎么来的 |
|---|---|---|
| 验收检查 | 全部通过（结构 23 项 + 实时 7 项） | `python -m scripts.check_m0 --live` |
| 离线单测 | 81 passed | 不联网、不需要 key，覆盖率 85% |
| 单次调用成本 | ¥0.006 | prompt ~2100（含 80 条候选）+ completion ~230 |
| 支持模型 | DeepSeek / Qwen / 本地 Ollama | `--provider` 一行切换 |

## M1 详情：评测集

| 产出 | 规模 | 位置 |
|---|---|---|
| 评分标准 | 4 维度 + 聚合规则 | [eval/rubric.md](../eval/rubric.md) |
| 评测 query | **200 条**（180 常规 + 20 边界） | [data/queries.csv](../data/queries.csv) |
| 理想答案要点 | **200 组**，每组 3–4 条 | [data/checklists.jsonl](../data/checklists.jsonl) |
| 候选池 | **80 条**，8 类目 × 10 | [data/candidates/pool_v1.csv](../data/candidates/pool_v1.csv) |
| 生成器 | 可复现（固定随机种子） | [scripts/gen_queries.py](../scripts/gen_queries.py) |

三个设计取舍：

1. **3 个客观维度 + 1 个语义维度**。日期、类目命中、类型数都能用代码算，交给模型只会引入方差；
   只有「理由是否引用了具体历史」必须靠 judge 判断。
2. **用候选池代替自由生成**。让模型自己编标题，`published_at` 也会是编的，时效性维度就失效了——
   测到的成了「模型编日期的水平」。候选池让模型只能从给定条目里挑，日期由代码填充。
3. **20 条边界案例**。无历史、单类目、兴趣冲突、条数限制、否定约束——正常用户不会这么问，
   但 judge 最容易在这些地方出错，也是 M5 回归集的来源。

设计过程中的 17 个问题与 6 类根因，记录在 [rubric-review.md](rubric-review.md)。

## M2 / M3 / M4 详情

- **M2**：见 [eval/REPORT.md](../eval/REPORT.md)（三个数字 + 结论 + 局限）
- **M3**：见 [README 的「看一次真实运行」](../README.md) 与 `python -m scripts.run_task --help`
- **M4**：见 [README 的安装/用法](../README.md) 与 [bugs.md](bugs.md) 中 BUG-011 ~ BUG-017
