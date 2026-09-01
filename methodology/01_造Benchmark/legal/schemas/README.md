# 法律 Benchmark Schema 目录

## 1. 目录用途

保存正式法律题目的 JSON Schema，用于约束字段是否存在、类型是否正确以及枚举值是否合法。

## 2. 文件说明

当前主要文件：

```text
question.schema.json
```

## 3. 重点字段

| 字段 | 含义 |
|---|---|
| `question_id` | 题目唯一编号。 |
| `case_id` | 案件编号，用于案件级 split。 |
| `split` | `dev`、`calibration` 或 `test`。 |
| `case_classification` | 案件级 taxonomy 信息。 |
| `task_type` | 题目任务类型。 |
| `answer_type` | 预期答案形式。 |
| `scoring_method` | 评分方式。 |
| `difficulty` | 难度。 |
| `risk_level` | 风险等级。 |
| `reference_answer` | 参考答案。 |
| `rubric` | Rubric 对象。 |
| `source_evidence` | 来源证据数组。 |

## 4. 示例

```json
{"question_id":"legal_0001_01","case_id":"case_0001","split":"dev","source_evidence":[{"source_quote":"...","source_quote_sha256":"..."}]}
```

## 5. 上游和下游

候选题从 `data/datasets/<dataset_id>/drafts/` 进入正式题集前，由 `dataset.build` 和 `validation.validate` 共同检查。

## 6. 是否提交 Git

Schema 是项目契约，应提交 Git。修改 Schema 时必须同步更新测试和 README。
