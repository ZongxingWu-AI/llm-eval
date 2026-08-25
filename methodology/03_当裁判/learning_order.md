# 03 当裁判学习顺序：法律 Benchmark

1. 阅读 ``legal_scorer.py`` 和评分 Prompt，先理解规则评分的输入输出。
2. 用固定的内存样例检查关键结论、拒答和引用缺失如何影响结果。
3. 运行少量评测，比较规则评分与 Rubric Judge。
4. 在 calibration 集上进行人工独立评分，记录误判并冻结 Prompt、Rubric 和模型版本。
