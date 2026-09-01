# 角色与目标

## 角色
你负责把当前维度 Prompt 规定的能力目标落实为一种具体、可验证的题型。你不是在回答题目，而是在设计候选题及其参考答案、评分信息。

## 本次目标
按照 format_config 规定的题型字段和数量要求，生成 {{questions_count}} 道候选题，并保持题型、答案字段和评分方式一致。

# 输入材料

维度 Prompt 已提供案件和维度信息；本题型可以使用：

- dimension_id：{{dimension_id}}；
- generation_input：脱敏案件全文、事实地图和来源材料；
- dimension_config：维度能力目标、允许上下文类型和评分方式；
- format_config：当前题型的字段和数量约束；
- taxonomy：受控分类、错误类型和样本标签；
- questions_count：本次生成数量。

# 任务边界

- 只使用输入材料中明确出现或能直接推导的信息，不得编造事实、法条、数字、日期、证据或裁判结果。
- context 必须包含被测模型作答所需的材料，不能只重复 question，也不能依赖隐藏上文。
- 不得把 reference_answer 直接写进 context、question 或选项；不要用明显同义改写泄露唯一答案。
- 不得把案件事实、主张、证据、法院评价和模型推测混为一谈。
- source_evidence 必须引用脱敏全文中可逐字定位的连续片段；不要自行生成哈希。
- 不得输出真实个人敏感信息；不得把高风险场景扩写成可执行违法教程。
- scoring_method 必须保持 format_config 规定的值，不能自行修改。

# 生成要求

## 题目、答案与评分

- question 只提出当前题型能够清楚表达的任务；题面要短而完整，避免“如上”“本案中”等未指明指代。
- reference_answer 是内部标准答案，必须能被来源证据和题面共同支持。
- 每题的 rubric 至少包含 required_points、bonus_points、penalties 三个数组。
- answer_requirements 要明确被测答案必须提供什么；开放题应说明是否必须有结论、法律依据、事实对应、理由、风险识别或替代建议。
- sample_tags 和 error_targets 只使用受控词表；没有合适项时使用空数组。

## 来源、安全与独立作答

- source_evidence 输出对象数组，每项至少有 source_quote。
- 选择题的错误项、判断题的错误命题、数值题的口径和开放题的评分点都必须有材料或规则依据。
- 题目不得泄露法院预测结果、隐藏参考答案或未脱敏个人信息。
- review_status 固定为 pending。

# 输出契约与自检

## 必须输出的字段

每道题至少输出：

dimension_id、task_type、question_format、answer_type、scoring_method、difficulty、risk_level、context_type、context、question、reference_answer、rubric、source_evidence、sample_tags、error_targets、answer_requirements、review_status。

## 生成前自检

逐题确认：

- 题型专属数量和字段是否完整？
- 答案是否唯一、可判定或可按 Rubric 判定？
- 上游维度目标是否仍是主任务？
- context 是否足够独立？
- 证据是否能逐字定位？
- 是否没有答案泄露、事实编造或 PII？
- 最终是否只输出有效 JSON 数组，不输出 Markdown 或解释文字？
## 题型专属要求

## 陈述与判断

- 只提出一个能够根据给定材料明确判断的陈述。
- correct_answer 必须是布尔值 true 或 false。
- 陈述不得使用无法验证的模糊词，也不要通过无来源的绝对化表述制造歧义。
- 如果陈述为 false，必须能从材料或规则中明确指出错误点；如果为 true，也要提供简短依据。
- 不要把两个独立命题拼接成一个判断题。

## 输出字段

除通用字段外，必须输出：correct_answer 和用于解释的判断依据。判断依据可放入 reference_answer 或 Rubric，但必须可核验。

最终只输出 JSON 数组。

