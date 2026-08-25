# 法律正式题集 releases 目录

## 1. 目录用途

保存经过人工审核、taxonomy 校验和来源定位校验的正式法律题集。评测模块默认从这里读取题目。

## 2. 数据来源和文件命名

输入来自 `../drafts/`，默认正式题集文件为：

```text
legal_questions.jsonl
```

## 3. JSONL 文件说明

每一行是一道正式题。相同 `case_id` 的所有题目必须拥有同一个 `split`。

## 4. 必要字段

正式题应包含：

```text
question_id
case_id
split
case_classification
primary_issue
task_type
reasoning_capabilities
answer_type
scoring_method
difficulty
risk_level
question
reference_answer
rubric
source_evidence
```

## 5. 重点字段说明

| 字段 | 含义 |
|---|---|
| `reference_answer` | 脱敏后的参考答案或答案要点。 |
| `rubric` | 评分标准，包括必答点、加分点和扣分项。 |
| `source_evidence` | 支撑题目和答案的章节、短引用或定位信息。 |
| `split` | `dev`、`calibration` 或 `test`。 |
| `case_id` | 用于保证案件级划分，不允许同案跨 split。 |

## 6. 示例

```json
{"question_id":"legal_0001_01","case_id":"case_0001","split":"dev","reference_answer":"...","rubric":{"required_points":["..."],"penalties":[]},"source_evidence":[{"source_section":"court_reasoning","source_quote":"..."}]}
```

## 7. 发布限制

正式 release 可以包含脱敏题目、参考答案、Rubric、来源哈希和必要短引用，但不能包含：

- 未审核的原始判决全文；
- 未审核候选题；
- API key、环境变量和本地绝对路径；
- 未经确认可以公开的个人隐私信息。

## 8. 是否提交 Git

只有完成来源、隐私、质量和人工审稿的 release 才能提交 Git。
