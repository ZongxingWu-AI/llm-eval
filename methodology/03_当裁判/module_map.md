# 03 当裁判模块地图：法律 Benchmark

| 小类 | 实际文件 | 输入 | 输出 |
|---|---|---|---|
| 规则评分 | ``methodology/03_当裁判/legal/scoring/legal_scorer.py`` | 模型回答、题目、Rubric | 规则分和命中信息 |
| 法律红线 | ``methodology/03_当裁判/legal/scoring/legal_scorer.py`` | 拒答词、关键结论和法条 | REVIEW/REJECT 依据 |
| Rubric Judge | ``methodology/03_当裁判/legal/scoring/legal_scorer.py`` + ``methodology/01_造Benchmark/legal/prompts/legal_scorer_rubric.md`` | 回答与评分标准 | PASS/REVIEW/REJECT |
| 人工 Calibration | ``methodology/01_造Benchmark/legal/data`` 和结果目录 | 人工标签、自动评分 | 校准对照材料 |
