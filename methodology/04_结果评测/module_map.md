# 04 结果评测模块地图：法律 Benchmark

| 模块 | 实际文件 | 输入 | 输出 | 关键职责 |
|---|---|---|---|---|
| 单题评分器 | `methodology/04_结果评测/legal/scoring/legal_scorer.py` | release 题目、`model_answer`、可选 JUDGE | `score_one` 评分字典 | 保留 `rule`、`redline`、`rubric_judge` 判分语义 |
| 批量结果评测 | `methodology/04_结果评测/legal/scoring/run.py` | 指定 release、`legal_model_outputs.jsonl` | `legal_evaluation_results.jsonl`、`legal_evaluation_errors.jsonl` | 按 `question_id` 配对，失败不中断且保留原答 |
| 分层报告 | `methodology/04_结果评测/legal/scoring/run.py` | 评分结果 | Markdown 报告 | 按 split、任务、维度、案件类别、难度、风险汇总 |
| Excel 导出 | `methodology/04_结果评测/legal/scoring/excel_export.py` | 评分 JSONL | `legal_evaluation_results.xlsx` | 便于筛选、人工复核和交付 |
| 人工复核 | 评分结果目录 + release | REVIEW/ERROR 原答和评分理由 | 复核记录和准入结论 | 解释边界题、错误题和高风险题 |

04 只相信指定 release 的题目元数据，不相信回答文件里可能被篡改的 `question`、维度或任务字段。回答与题目的唯一关联键是 `question_id`。
