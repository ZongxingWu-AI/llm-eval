# 法律 Benchmark 运行结果目录

## 1. 目录用途

保存法律评测阶段的模型回答、评分、错误记录、报告和运行元数据。每次运行可以放在一个带时间戳的子目录中。

## 2. 数据来源

输入来自 `data/releases/legal_questions.jsonl`，模型回答由被测模型生成，评分由规则、红线或 Rubric Judge 完成。

## 3. 文件说明

| 文件 | 含义 |
|---|---|
| `legal_results.jsonl` | 每道题一条回答和评分结果。 |
| `errors.jsonl` | 模型调用、JSON 解析或评分失败记录。 |
| `legal_report.md` | 按 split、任务类型和 verdict 汇总的 Markdown 报告。 |
| `run_metadata.json` | 输入、输出、模型、时间和运行参数。 |

## 4. JSONL 字段说明

常见字段包括：

```text
question_id
case_id
split
model
answer
reference_answer
scoring_method
score
verdict
reason
latency_seconds
tokens
error
```

| 字段 | 含义 |
|---|---|
| `question_id` | 正式题目编号。 |
| `case_id` | 来源案件编号。 |
| `split` | dev、calibration 或 test。 |
| `answer` | 被测模型的回答。 |
| `scoring_method` | 实际采用的评分器。 |
| `score` | 评分器给出的分数或等级。 |
| `verdict` | 通过、拒绝、错误等结果。 |
| `reason` | 评分理由。 |
| `error` | 调用或处理错误。 |

## 5. 示例

```json
{"question_id":"legal_0001_01","case_id":"case_0001","split":"test","scoring_method":"rubric_judge","score":4,"verdict":"pass","reason":"覆盖必答点","error":""}
```

## 6. 是否提交 Git

除本 README 外，运行结果默认被 `.gitignore` 忽略，避免提交模型输出、隐私和本地运行信息。
