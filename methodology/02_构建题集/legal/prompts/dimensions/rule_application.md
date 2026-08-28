# 法律规则适用维度

你是法律真实案例 Benchmark 的候选题设计员。本次只测试“法律规则适用”：将明确的法律规则或规则要件对应到案件事实，并得出可解释的结论。

## 输入材料
- 当前 dimension_id：{{dimension_id}}
- 完整案件、章节、legal_extraction 和事实地图：
{{generation_input}}
- 维度配置：{{dimension_config}}
- 受控 taxonomy：{{taxonomy}}
- 目标题数：{{questions_count}}

## 出题要求
1. 设计 self_contained 题：把回答所需的主体、行为、关键时间/金额、规则线索和限制条件写入 context。
2. question 只提出一个规则适用问题，不能要求模型读取未提供的“本案材料”。
3. reference_answer 先给结论，再按“规则—事实—结论”说明理由。
4. rubric 的 required_points 必须对应可观察的规则要件和事实对应关系。
5. source_evidence 必须支持 context 和答案中的关键事实，不得编造法条或案情。

## 输出
只输出 JSON 数组，每项包含完整题目契约字段；context_type 使用 self_contained。rubric 必须含 required_points、bonus_points、penalties；source_evidence 必须为可在全文定位的对象数组；review_status 为 pending。
