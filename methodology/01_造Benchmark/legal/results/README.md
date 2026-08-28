# results：法律 Benchmark 运行结果

## 目录职责

`results/` 保存 03 模型作答和 04 结果评测针对某个正式题集的一次或多次独立运行。每次运行使用独立目录，不覆盖其他运行，也不写入 `data/` 的冻结题集。

## 03 模型作答产物

| 文件 | 内容 |
|---|---|
| `legal_model_outputs.jsonl` | 每道成功题的原始模型回答和调用元数据 |
| `legal_model_errors.jsonl` | 被测模型调用失败记录 |
| `run_metadata.json` | release 路径、release SHA-256、contestant 模型、时间和计数 |

## 04 结果评测产物

| 文件 | 内容 |
|---|---|
| `legal_evaluation_results.jsonl` | 每道题的原始回答、评分结果和 scoring_details |
| `legal_evaluation_errors.jsonl` | 规则、红线或裁判评分失败记录，含原始回答关联信息 |
| `legal_evaluation_report.md` | 按 split、任务类型和 verdict 汇总的报告 |
| `legal_evaluation_results.xlsx` | 结果表格导出，生成失败不影响 JSONL |
| `run_metadata.json` | release 路径、release SHA-256、回答文件、裁判模型、时间和计数 |
| `excel_error.txt` | Excel 导出失败时的错误说明，可选 |

评分阶段必须重新读取正式 release，使用 `question_id` 与原始回答一一匹配；不能只依赖回答文件中的题目文本。更换裁判配置不会触发 contestant API 调用。
