# 任务库常用 SQL

> 数据库：SQLite，本地 `data/tasks.db`、容器 `data/tasks-container.db`
> 工具：`sqlite3`（系统自带）、DBeaver，或 `python -m scripts.inspect_db`
>
> 表结构：
> ```
> tasks(id, qid, status, result, trace, steps, cost_cny, created_at, trace_id)
> ```
> `trace` 是 JSON 数组，每项 `{step, tool, args, ok, error, result, latency_ms}`。
> SQLite 自带 JSON 函数，可以直接把 trace 拆开统计。

## 一、总览

```sql
-- 按状态统计
SELECT status, COUNT(*) AS n, ROUND(SUM(cost_cny),4) AS total_cost
FROM tasks GROUP BY status ORDER BY n DESC;

-- 每天跑了多少
SELECT substr(created_at,1,10) AS day, COUNT(*) AS n,
       ROUND(SUM(cost_cny),4) AS cost
FROM tasks GROUP BY day ORDER BY day DESC;
```

## 二、列表与详情

```sql
-- 最近 10 条
SELECT id, qid, status, steps, ROUND(cost_cny,5) AS cost, trace_id, created_at
FROM tasks ORDER BY id DESC LIMIT 10;

-- 某条任务的结论
SELECT id, qid, result FROM tasks WHERE id = 9;

-- 把某条任务的轨迹展开成表格
SELECT json_extract(t.value,'$.step')       AS step,
       json_extract(t.value,'$.tool')       AS tool,
       json_extract(t.value,'$.latency_ms') AS ms,
       json_extract(t.value,'$.ok')         AS ok,
       json_extract(t.value,'$.error')      AS err
FROM tasks, json_each(tasks.trace) t
WHERE tasks.id = 9
ORDER BY step;
```

## 三、成本

```sql
-- 总体成本
SELECT COUNT(*) AS tasks,
       ROUND(SUM(cost_cny),4) AS total,
       ROUND(AVG(cost_cny),5) AS avg,
       ROUND(MIN(cost_cny),5) AS min,
       ROUND(MAX(cost_cny),5) AS max
FROM tasks;

-- 最贵的 5 次
SELECT id, qid, ROUND(cost_cny,5) AS cost, steps
FROM tasks ORDER BY cost_cny DESC LIMIT 5;
```

## 四、性能（需要 JSON 函数）

```sql
-- 各工具的平均/最慢耗时与失败次数
SELECT json_extract(t.value,'$.tool')                               AS tool,
       COUNT(*)                                                     AS calls,
       ROUND(AVG(json_extract(t.value,'$.latency_ms')))             AS avg_ms,
       MAX(json_extract(t.value,'$.latency_ms'))                    AS max_ms,
       SUM(CASE WHEN json_extract(t.value,'$.ok')=0 THEN 1 ELSE 0 END) AS errors
FROM tasks, json_each(tasks.trace) t
GROUP BY tool
ORDER BY avg_ms DESC;

-- 最慢的 5 个步骤
SELECT tasks.id AS task, tasks.qid,
       json_extract(t.value,'$.tool')       AS tool,
       json_extract(t.value,'$.latency_ms') AS ms
FROM tasks, json_each(tasks.trace) t
ORDER BY ms DESC LIMIT 5;
```

## 五、失败与异常

```sql
-- 非 done 的任务
SELECT id, qid, status, steps, ROUND(cost_cny,5) AS cost
FROM tasks WHERE status <> 'done' ORDER BY id DESC;

-- 出现过工具错误的步骤（错误存在 trace 里）
SELECT tasks.id AS task, tasks.qid,
       json_extract(t.value,'$.tool')  AS tool,
       json_extract(t.value,'$.error') AS error
FROM tasks, json_each(tasks.trace) t
WHERE json_extract(t.value,'$.ok') = 0
ORDER BY tasks.id DESC;

-- 步数超过 4 的任务（说明模型多绕了路）
SELECT id, qid, steps FROM tasks WHERE steps > 4 ORDER BY steps DESC;
```

## 六、导出

```bash
# 导出 CSV（Excel/Numbers 可直接打开）
sqlite3 -header -csv data/tasks.db \
  "SELECT id,qid,status,steps,cost_cny,created_at FROM tasks;" > tasks.csv
```

## 命令行里怎么执行

```bash
# 单条
sqlite3 -header -column data/tasks.db "SELECT id,qid,status FROM tasks LIMIT 5;"

# 多条（用 heredoc，避免 $ 被 shell 吃掉）
sqlite3 -header -column data/tasks.db <<'SQL'
SELECT json_extract(t.value,'$.tool') AS tool, COUNT(*) AS n
FROM tasks, json_each(tasks.trace) t
GROUP BY tool;
SQL
```

> 注意：SQL 里写 `'$.tool'` 要用**单引号**，否则 shell 会把 `$` 当变量展开。

## 实测结果（2026-11-05，9 条任务）

```
status  n  total_cost        工具               calls  avg_ms  max_ms  errors
done    9  0.0549           generate_recs      10     2937    4180    2
                            score_with_rubric   9     2081    2664    1
                            (final)             9     1420    2062    0
                            metrics_calc        9     1126    1915    1

成本：总 ¥0.0549，平均 ¥0.0061/次，区间 ¥0.0050–0.0080
```

**两条能直接用的结论**：

1. `generate_recs` 占了总耗时的大头（平均 2937ms），是性能瓶颈
2. 它的 10 次调用里有 2 次失败（分别是 BUG-011 的签名错误和一次重试）——`calls` 比别的工具多 1，正是那次重试
