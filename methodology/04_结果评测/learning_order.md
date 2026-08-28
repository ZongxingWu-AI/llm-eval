# 04 结果评测学习顺序：法律 Benchmark

1. 先阅读 `legal/scoring/legal_scorer.py`，理解 `rule`、`redline` 和 `rubric_judge` 的输入、输出与判分边界。
2. 阅读批量入口，确认它从指定 release 读取题面、参考答案、Rubric 和评分方法，而不是只依赖回答文件。
3. 检查 `question_id` 的缺失、重复和无法匹配如何报错；确认 04 不创建 contestant、不调用 contestant API。
4. 用同一份 `legal_model_outputs.jsonl` 分别使用两个 JUDGE 配置评分，比较评分理由和详情，理解数据级解耦。
5. 检查评分失败时结果仍保留 `model_answer`，错误记录如何进入人工复核清单。
6. 阅读报告和 Excel 导出，重点看 `dimension_id`、案件类别、难度和风险分层，而不是只看混合总分。
7. 在 calibration 集完成人工对照后，再只评测冻结的 test split，并据此做准入、限用或复测决策。
