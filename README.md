# 推荐质量 Agent（Rec-Quality Agent）

给一个用户请求 → Agent 生成推荐 → 多维度打分 → 输出质量问题与改进建议，且每次改动都被 CI 回归校验。

> 当前进度：**M0（环境与数据）** —— 已经能跑通一次「生成 5 条推荐」的 LLM 调用。

## 目录结构

```
rec-quality-agent/
├── app/                     # 应用代码（分层：配置 → 能力 → 业务 → 入口）
│   ├── config.py            # 集中配置：路径、provider、超时、条数（唯一的 os.getenv 出口）
│   ├── prompts.py           # prompt 模板（M1/M2 会反复调，独立成文件）
│   ├── llm.py               # 客户端工厂：deepseek / qwen / ollama + 成本估算
│   ├── recs.py              # 业务：generate_recs() 生成 N 条推荐并解析
│   ├── agent.py             # M3：规划-工具-产出循环
│   ├── main.py              # M3：FastAPI 入口
│   ├── store.py             # M3：SQLite 任务与轨迹
│   ├── logging.py           # M4：结构化日志
│   └── tools/               # M3：metrics.py / sql_query.py
├── eval/                    # 评测（M2）
│   ├── rubric.md            # 评分标准
│   ├── judge.py             # 双 judge 打分
│   ├── agreement.py         # kappa / 位置偏差
│   └── REPORT.md            # 1 页评测报告
├── data/
│   ├── queries.csv          # 200 条评测 query（M1）
│   ├── labels.csv           # 人工标注（M2）
│   └── raw/                 # 公开数据集，不进 git
├── scripts/
│   └── smoke_recs.py        # M0 验收脚本：跑通一次生成 5 条推荐
├── tests/                   # pytest，全部离线，不需要 key
├── .github/workflows/       # M5：CI 回归门禁
├── pytest.ini               # testpaths + pythonpath，省掉 conftest 的 sys.path 技巧
└── requirements.txt

## 快速开始

要求 **Python 3.10+（原生 arm64）**。不要用默认的 `python3`：如果是通过 Rosetta 运行的 x86_64 解释器，macOS 会拒载 pandas 的 x86 wheel，报 `library load disallowed by system policy`。

```bash
/usr/local/bin/python3.10 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env      # 填一个 key（DeepSeek 或 Qwen），.env 已被 .gitignore 排除

.venv/bin/python -m pytest                    # 离线单测，不需要 key
.venv/bin/python -m scripts.smoke_recs --dry-run   # 只检查配置和 prompt
.venv/bin/python -m scripts.smoke_recs             # 真实调用：生成 5 条推荐
.venv/bin/python -m scripts.check_m0                # M0 验收：21 项结构检查
.venv/bin/python -m scripts.check_m0 --live -n 3    # 额外评估输出质量与稳定性
```

成功输出末行是 `条数：5（期望 5）` 与成本估算；退出码 0=成功、1=条数不对/连接失败、2=key 缺失或无效。

没有 key 也可以用本地模型：

```bash
ollama serve &          # 另开终端
ollama pull qwen2.5:7b
.venv/bin/python -m scripts.smoke_recs --provider ollama
```

## 遇到问题

环境、网络、解释器相关的坑和验证过的解法，见 [docs/troubleshooting.md](docs/troubleshooting.md)。

## 开发约定

- 所有配置集中在 `app/config.py`，其他模块不要直接读环境变量
- prompt 文案只放 `app/prompts.py`，方便做版本对比与位置偏差实验
- 单测必须离线可跑（不联网、不需要 key），CI 才能稳定
- commit 前缀：`feat(scope):` / `fix(scope):` / `docs(scope):` / `test(scope):`
