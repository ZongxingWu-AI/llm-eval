# 法律候选题 drafts 目录

## 1. 目录用途

保存由模型或人工生成的候选法律题，供人工审核和后续正式题集组装使用。

## 2. 数据来源和文件命名

输入来自 `../cleaned/`，默认输出为：

```text
candidate_questions.jsonl
```

## 3. JSONL 文件说明

每一行对应一道候选题。一个案件可以对应多道题，但正式 split 时仍以 `case_id` 为单位。

## 4. 字段说明

| 字段 | 含义 |
|---|---|
| `question_id` | 正式题集使用的题目 ID；草稿阶段可能为空。 |
| `case_id` | 题目所依据的案件 ID。 |
| `case_classification` | 案件级领域、案由、审级和标签。 |
| `primary_issue` | 主要法律争议焦点。 |
| `task_type` | 题目要求完成的任务类型。 |
| `reasoning_capabilities` | 需要考查的推理能力。 |
| `answer_type` | 预期答案形式。 |
| `scoring_method` | `rule`、`redline` 或 `rubric_judge`。 |
| `difficulty` | `easy`、`medium` 或 `hard`。 |
| `risk_level` | `low`、`medium` 或 `high`。 |
| `question` | 给被测模型的题目。 |
| `reference_answer` | 参考答案或答案要点。 |
| `rubric` | 必答点、加分点、扣分项和评分规则。 |
| `source_evidence` | 来源章节和原文引用定位。 |
| `review_status` | `pending` 表示待审，`approved` 表示审核通过。 |

## 5. 示例

```json
{"question_id":"","case_id":"case_0001","primary_issue":"逾期付款利息起算时间","question":"请说明法院如何确定利息起算时间。","reference_answer":"...","rubric":{"required_points":["说明起算日"]},"source_evidence":[{"source_section":"court_reasoning","source_quote":"..."}],"review_status":"pending"}
```

## 6. 上游和下游

只有 `review_status=approved` 且通过 taxonomy 校验的题目才能进入 `../releases/`。

## 7. 是否提交 Git

除本 README 外默认不提交。候选题可能包含尚未审核的模型生成内容。
