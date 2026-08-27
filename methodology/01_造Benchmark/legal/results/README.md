# results：法律 Benchmark 评测运行结果

## 目录职责

`results/` 保存 evaluation 阶段针对某个正式题集和模型配置的一次独立运行结果。每次运行使用独立目录，不覆盖其他运行，也不写入 `data/` 的冻结题集。

评测输入默认为：

```text
data/releases/legal_questions_release_v1.jsonl
```

## 当前运行产物

| 文件 | 内容 |
|---|---|
| `legal_evaluation_results.jsonl` | 每道题一条模型回答和评分结果 |
| `legal_evaluation_errors.jsonl` | 模型调用、JSON 解析或评分失败记录 |
| `legal_evaluation_report.md` | 按 split、任务类型和 verdict 汇总的报告 |
| `legal_evaluation_results.xlsx` | 结果表格导出，生成失败不影响 JSONL |
| `run_metadata.json` | 输入题集、模型、时间和计数等运行元数据 |
| `excel_error.txt` | Excel 导出失败时的错误说明，可选 |

## 命名规范

评测 JSONL 使用与全链路一致的语义化命名：

```text
legal_evaluation_results.jsonl
legal_evaluation_errors.jsonl
```

结果文件不能简称为 `results.jsonl` 或 `errors.jsonl`，因为运行目录可能被单独复制或汇总。主结果文件与 Excel 使用同一实体名；错误文件明确属于 evaluation 阶段。

## 重点字段

| 字段 | 说明 |
|---|---|
| `question_id` / `case_id` | 题目和来源案件标识 |
| `split` | `dev`、`calibration` 或 `test` |
| `question` / `model_answer` | 输入题目和被测模型回答 |
| `reference_answer` | 题集中的参考答案 |
| `scoring_method` | 实际采用的评分方式 |
| `verdict` / `reason` | 判定结果和判定理由 |
| `latency_seconds` / `total_tokens` | 调用性能和 token 统计 |
| `error` | 单题失败信息；详细失败记录见错误 JSONL |

## 最小示例

```json
{"question_id":"legal_case_0001_01","case_id":"case_0001","split":"test","scoring_method":"rubric_judge","verdict":"PASS","reason":"满足全部必答点","latency_seconds":0.42,"total_tokens":128}
```

## 追溯与安全

`run_metadata.json` 必须能回到具体 release 文件和模型配置。结果目录不得写入 API key；正式报告发布前应检查模型回答中是否包含不应公开的原文或个人信息。

## Git 策略

运行结果默认由 `.gitignore` 忽略。需要提交时，应保留输入 release 版本、运行元数据和结果文件之间的对应关系，不能只提交脱离上下文的分数摘要。
