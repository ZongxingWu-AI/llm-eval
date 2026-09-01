# releases：冻结后的正式题集

`releases/` 保存经审核、按题集蓝图组装、通过校验并版本化冻结的正式题集。它是 03 模型作答和 04 结果评测共同使用的稳定输入，不能由后续运行覆盖；04 也不能只依赖回答文件中的题目文本。

## 题目字段

正式题目的结构以 `methodology/01_造Benchmark/legal/schemas/question.schema.json` 为准，关键字段分为四组：

- 身份与划分：`question_id`、`case_id`、`split`；
- 维度与任务：`dimension_id`、`task_type`；
- 材料与问题：`context_type`、`context`、`question`；
- 参考与评分：`reference_answer`、`rubric`、`source_evidence`、`scoring_method`、`difficulty`、`risk_level`。

`dimension_id` 是九类能力维度的稳定统计键；`task_type` 是面向用户的任务分类；`context_type` 决定 03 如何给模型组织材料。`question` 不应依赖未提供的“上文”。

`source_evidence` 的每个条目至少包含 `source_quote`，可附带由本地程序生成的 `source_quote_sha256`；引用直接在案件脱敏全文 `external_text` 中逐字回溯。参考答案和法院结论不得泄露到裁判结果预测题的 `context` 中。

## 九类维度

```text
事实抽取、争议焦点识别、法律规则适用、证据评价、
裁判结果预测、法律论证、金额计算、合规拒答、程序与时间推理
```

题集按 `dimension_catalog.json` 中的蓝图配额组装；每案不要求覆盖全部维度。发布清单和 metadata 应记录维度计数、配额缺口、案件类别、难度和风险覆盖。

## 推荐文件

```text
legal_questions_release_v1.jsonl
legal_questions_release_v1.rejected.jsonl
legal_release_manifest_v1.json
legal_questions_release_v1.jsonl.metadata.json
```

## 运行 03 模型作答

```powershell
$repo = "C:\llm-eval"
$dataset = "$repo\methodology\01_造Benchmark\legal\data\datasets\legal_20260827_001"
$answerRun = Join-Path $env:TEMP "legal-model-answer-run"
Set-Location $repo
py -m methodology.03_模型作答.legal.evaluation.run `
  --input "$dataset\releases\legal_questions_release_v1.jsonl" `
  --output $answerRun
```

03 输出 `legal_model_outputs.jsonl`、`legal_model_errors.jsonl` 和 `run_metadata.json`。它只调用 contestant，不评分。

## 运行 04 结果评测

```powershell
$scoreRun = Join-Path $env:TEMP "legal-result-scoring-run"
py -m methodology.04_结果评测.legal.scoring.run `
  --questions "$dataset\releases\legal_questions_release_v1.jsonl" `
  --outputs "$answerRun\legal_model_outputs.jsonl" `
  --output $scoreRun
```

04 输出评分结果、错误、Markdown 报告、Excel 和评分运行元数据。更换裁判模型或评分逻辑时，直接重跑 04，不重新调用被测模型。
