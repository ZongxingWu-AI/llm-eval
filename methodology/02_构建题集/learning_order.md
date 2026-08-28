# 02 构建题集学习顺序：法律 Benchmark

1. 先读 `legal/config/dimension_catalog.json`，理解九类维度、`dimension_id`、`task_type`、二级能力标签、上下文类型、评分方法和题量蓝图。
2. 阅读 extract 数据，确认案件全文、章节、事实地图和来源引用如何进入统一出题引擎；不要只看少量命中的片段。
3. 阅读每个维度 Prompt，理解该维度测什么、需要哪些事实、参考答案要点是什么，以及哪些内容不能泄露。
4. 先用少量案件按维度生成候选题；每个维度可以独立产出候选题，但读写、重试、错误处理和证据校验仍由同一个引擎完成。
5. 人工检查 `context + question` 是否足以作答，确认题目不依赖隐藏的“上文”，并核对 `source_evidence` 能在原文定位。
6. 检查答案、Rubric、法条版本、难度、风险和 `reasoning_capabilities`，将合格题标记为 `approved`。
7. 运行 `build.py`，按蓝图配额组装 release；重点查看 `dimension_counts`、配额缺口、案件类别、难度和风险覆盖。
8. 运行 `validate.py`，修复所有关键失败和答案泄露问题。通过校验的冻结 release 才能交给 03。

学习重点：维度是统一流水线的配置入口，不是九份重复代码；题目是“材料 context + 问题 question”，而不是把所有背景都隐含在 question 里。
