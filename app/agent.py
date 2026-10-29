"""M3：规划 → 选工具 → 执行 → 判断完成的循环。

约定接口：run_task(task, max_steps=6) -> {result, trace, tokens, cost}
三个工具：generate_recs（app/recs.py 已有）、metrics_calc、score_with_rubric。
"""
