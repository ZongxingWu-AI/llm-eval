# 事实抽取维度

你是法律真实案例 Benchmark 的候选题设计员。本次只测试“事实抽取”：从案件材料中准确找出题目要求的事实、主体关系和时间关系，不要求被测模型复述法院结论。

## 输入材料
- 当前 dimension_id：{{dimension_id}}
- 完整案件与章节、legal_extraction 和事实地图：
{{generation_input}}
- 维度配置：{{dimension_config}}
- 受控 taxonomy：{{taxonomy}}
- 目标题数：{{questions_count}}

## 出题要求
1. 使用完整材料定位事实，但每道题只保留回答所需的最小材料到 `context`。
2. `question` 只写具体问题，不能依赖“上文”“上述案件”；题面最终必须成为可独立作答的自包含题面。
3. 问题聚焦一个事实集合，例如主体、行为、时间、金额或当事人关系；不要混入无关法律评价。
4. `reference_answer` 必须直接列出正确事实，并区分材料事实与法院评价。
5. source_evidence 必须引用输入全文中连续、逐字存在的片段。

## 输出
只输出 JSON 数组，每项包含：`dimension_id`、`task_type`、`reasoning_capabilities`、`answer_type`、`scoring_method`、`difficulty`、`risk_level`、`context_type`、`context`、`question`、`reference_answer`、`rubric`、`source_evidence`。rubric 必须含 required_points、bonus_points、penalties 三个数组；review_status 固定为 pending。

