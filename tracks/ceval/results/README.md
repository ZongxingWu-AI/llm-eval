# C-Eval 运行结果目录

## 1. 目录用途

本目录保存 C-Eval 每次运行生成的逐题结果、错误记录、报告和运行元数据。每次运行通常使用一个带时间戳的子目录。

## 2. 数据来源

输入来自 `tracks/ceval/data/`，模型原始回答来自 C-Eval 评测调用。

## 3. 文件命名规则

常见文件包括：

```text
ceval_results.jsonl
errors.jsonl
ceval_report.md
run_metadata.json
```

## 4. JSONL 文件说明

每一行对应一道题。准确率由所有逐题记录中的 `correct=true` 数量除以有效题目总数得到。

## 5. 字段说明

| 字段 | 含义 |
|---|---|
| `question_id` 或 `id` | 题目编号。 |
| `question` | 题干，方便报告回溯。 |
| `model` | 被测模型名称。 |
| `raw_output` | 模型原始文本。 |
| `predicted_answer` | 从原始文本中解析出的选项。 |
| `correct_answer` | 数据集中的标准答案。 |
| `correct` | 是否答对，布尔值。 |
| `latency_seconds` | 本题模型调用延迟。 |
| `tokens` | 本题使用的 token 数。 |
| `finish_reason` | 模型接口返回的结束原因。 |
| `error` | 本题错误信息；空字符串表示无错误。 |

## 6. 示例

```json
{"id":"computer_network-0000","model":"example-model","raw_output":"C","predicted_answer":"C","correct_answer":"C","correct":true,"latency_seconds":1.2,"tokens":80,"finish_reason":"stop","error":""}
```

## 7. 上游和下游

结果可以被报告模块和 `tools.export_excel` 读取，但不会反写题目数据。

## 8. 是否提交 Git

除本 README 外，运行结果默认被 `.gitignore` 忽略，不提交模型回答和运行产物。
