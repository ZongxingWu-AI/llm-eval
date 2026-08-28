# 03 模型作答：法律 Benchmark 原始回答

03 的唯一职责是把冻结后的正式 release 交给被测模型，保存每道题的原始回答。它不负责判分，也不创建 JUDGE 客户端。

## 输入与上下文策略

输入：正式 release JSONL + contestant 配置。

每题使用 `context_type` 组织被测模型输入：

| context_type | 实际输入 |
|---|---|
| `self_contained` | `context`（必要背景） + `question` |
| `source_excerpt` | `context`（原文材料/片段） + `question` |
| `full_document` | `context`（完整案件材料） + `question` |
| `scenario` | `context`（风险场景） + `question` |

`reference_answer`、`rubric` 和 `source_evidence` 不发送给被测模型。旧题缺少 `context` 时，测试环境可回退为原有 `question` 输入；新正式题必须显式提供可作答的 `context`。

release 的 dimension_id 统一来自九类法律能力：事实抽取、争议焦点识别、法律规则适用、证据评价、裁判结果预测、法律论证、金额计算、合规拒答、程序与时间推理。03 不改变这些维度，只把它们对应的材料和问题交给被测模型。

## 输出

```text
legal_model_outputs.jsonl
legal_model_errors.jsonl
run_metadata.json
```

成功记录至少保存：`question_id`、`case_id`、`split`、`dimension_id`、`task_type`、`context_type`、`difficulty`、`question`、`model_answer`、`latency_seconds`、`total_tokens` 和 `finish_reason`。失败记录保存题目关联键和调用错误，不影响其他题继续作答。

## 运行示例

```powershell
$repo = "C:\llm-eval"
$dataset = "$repo\methodology\01_造Benchmark\legal\data\datasets\<dataset_id>"
$answerRun = Join-Path $env:TEMP "legal-model-answer-run"
Set-Location $repo

py -m methodology.03_模型作答.legal.evaluation.run `
  --input "$dataset\releases\legal_questions_release_v1.jsonl" `
  --output $answerRun
```

03 完成后，不要在这里评分；把同一个 release 和 `legal_model_outputs.jsonl` 交给 04。更换裁判模型、评分 Prompt 或评分逻辑时，只重跑 04，不重新调用 contestant。

