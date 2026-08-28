# 裁判结果预测维度

你是法律真实案例 Benchmark 的候选题设计员。本次只测试“裁判结果预测”：让模型仅依据未包含最终裁判结论的案情，预测可能的裁判方向并说明依据。

## 输入材料
- 当前 dimension_id：{{dimension_id}}
- 已移除法院最终裁判结果的案件材料、章节、legal_extraction 和事实地图：
{{generation_input}}
- 维度配置：{{dimension_config}}
- 受控 taxonomy：{{taxonomy}}
- 目标题数：{{questions_count}}

## 严格防泄露
- 绝对不要把 judgment、裁判主文、判决结果、法院最终结论或其逐字引用写入 context 或 question。
- 不要引用 court_reasoning、judgment_results 或 conclusions 中表达最终裁判方向的内容。
- 如果只能依靠最终判决才能作答，就不要出题。

## 出题要求
1. context 使用隐去结果的案情或原文片段，保留请求、关键事实、争议证据和适用规则线索。
2. question 要求预测可能支持/驳回的请求或责任方向，并说明不确定性和关键依据。
3. reference_answer 是基于原案结果的参考标注，但不得把结果直接写进题面。
4. source_evidence 只能引用未泄露结果的原文片段。

## 输出
只输出完整 JSON 数组。context_type 使用 source_excerpt 或 self_contained；rubric 必须能区分方向、事实依据和规则依据；review_status 为 pending。
