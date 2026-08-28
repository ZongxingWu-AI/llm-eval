# 04 结果评测：法律回答评分与能力报告

04 读取正式 release 和 03 已保存的原始回答，按 `question_id` 一一匹配后独立评分。它不调用 contestant，也不依赖回答文件中的题目文本；题面、参考答案、Rubric、来源和评分方式以指定 release 为权威。

## 评分口径

保留三种既有语义：

- `rule`：规则化答案要点匹配，不需要 JUDGE。
- `redline`：合规/安全红线检查，不需要 JUDGE。
- `rubric_judge`：使用可选 JUDGE 按 release 中的 Rubric 评分。

输出结论为 `PASS`、`REVIEW` 或 `REJECT`。单题评分失败时继续处理其他题，并在结果中保留对应的 `model_answer`，错误另写入错误文件。

## 输入与输出

输入：正式 release JSONL + `legal_model_outputs.jsonl` + 可选 JUDGE 配置。

输出：

```text
legal_evaluation_results.jsonl
legal_evaluation_errors.jsonl
legal_evaluation_report.md
legal_evaluation_results.xlsx
run_metadata.json
```

结果至少包含 `question_id`、`dimension_id`、`context_type`、题目元数据、`model_answer`、`reference_answer`、`scoring_method`、`verdict`、`reason`、调用元数据和 `scoring_details`。

## 报告分层

报告不只给一个总体分数，还按以下字段汇总 PASS/REVIEW/REJECT/ERROR 和错误率：

- `split`
- `task_type`
- `dimension_id`
- 案件类别
- `difficulty`
- `risk_level`

同时生成人工复核清单，优先定位 `REVIEW` 和评分 `ERROR`。这样可以区分总体结果与事实抽取、规则适用、证据评价、金额计算、合规拒答等能力画像。

九类 dimension_id 均可独立汇总：事实抽取、争议焦点识别、法律规则适用、证据评价、裁判结果预测、法律论证、金额计算、合规拒答、程序与时间推理。报告中的维度名称和题目归属以正式 release 为准。

## 运行示例

```powershell
$repo = "C:\llm-eval"
$dataset = "$repo\methodology\01_造Benchmark\legal\data\datasets\<dataset_id>"
$answerRun = Join-Path $env:TEMP "legal-model-answer-run"
$scoreRun = Join-Path $env:TEMP "legal-result-scoring-run"
Set-Location $repo

py -m methodology.04_结果评测.legal.scoring.run `
  --questions "$dataset\releases\legal_questions_release_v1.jsonl" `
  --outputs "$answerRun\legal_model_outputs.jsonl" `
  --output $scoreRun
```

更换裁判模型、评分 Prompt 或评分逻辑时，只需重新运行 04；contestant API 调用次数为 0。

