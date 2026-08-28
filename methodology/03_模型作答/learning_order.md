# 03 模型作答学习顺序：法律 Benchmark

1. 先阅读正式 release 的题目契约，理解 `context` 和 `question` 的分工。
2. 阅读 `legal/evaluation/run.py`，确认四种 `context_type` 如何组织被测模型输入。
3. 检查发送内容不包含 `reference_answer`、`rubric`、`source_evidence`；预测裁判结果题的材料也不能包含法院最终结论。
4. 检查 `question_id`、`dimension_id`、`task_type`、`context_type`、模型原始回答、延迟、Token 和 finish reason 如何写入输出。
5. 用包含 `rubric_judge` 的题做 smoke，确认本阶段不创建或调用 JUDGE，也不执行 `score_one()`。
6. 用同一 release 重新运行 03 时，先明确这是一次新的 contestant 调用；如果只是更换裁判模型，应保留原始回答并直接进入 04。
