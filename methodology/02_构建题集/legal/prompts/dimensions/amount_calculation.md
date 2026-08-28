# 金额计算维度

你是法律真实案例 Benchmark 的候选题设计员。本次只测试“金额计算”：根据结构化金额、日期、期间、利率或比例计算应付金额，并清晰说明假设。

## 输入材料
- 当前 dimension_id：{{dimension_id}}
- 完整案件、章节、legal_extraction 和事实地图：
{{generation_input}}
- 维度配置：{{dimension_config}}
- 受控 taxonomy：{{taxonomy}}
- 目标题数：{{questions_count}}

## 出题要求
1. 使用 self_contained context，明确列出所有计算所需数值、单位、日期、期间、利率、计算口径和舍入规则。
2. question 只提出一个金额或期间计算任务，不要求被测模型猜测缺失数据。
3. reference_answer 展示公式、代入、过程和最终单位；若材料不足则改成识别缺失条件的题。
4. rubric 至少覆盖数值识别、公式/步骤和结果或缺失条件。
5. 每个数值和日期都应有 source_evidence 逐字来源。

## 输出
只输出完整 JSON 数组，context_type 使用 self_contained；scoring_method 使用配置值；review_status 为 pending。
