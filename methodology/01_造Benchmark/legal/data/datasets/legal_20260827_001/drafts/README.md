# drafts：候选题草稿

## 目录职责

`drafts/` 保存从本批次 `extract` 案件生成的候选题。候选题已经有题目结构，但仍可能存在事实、难度、答案或证据问题，默认需要审核，不能直接作为正式评测输入。

## 按题目 schema 对照字段

题目结构以 `legal/schemas/question.schema.json` 为准。`question_id`、`case_id`、`split` 是身份和划分字段；`case_classification`、`primary_issue`、`task_type`、`reasoning_capabilities`、`answer_type`、`scoring_method`、`difficulty`、`risk_level` 定义案件、任务和评测属性；`question`、`reference_answer`、`rubric`、`source_evidence` 是题面、参考答案、评分标准和证据定位。

其中 taxonomy 主要约束可统计、可复用的受控取值；案件事实、题面、答案和证据引用必须回到 extract 或原文，不可凭空补写。`source_evidence` 通常逐条包含 `source_section` 和 `source_quote`，用于回查案件章节。

## 状态区别

- `draft`：候选，允许 `pending`、需要修订或被拒绝；不保证已经冻结。
- `release`：通过结构校验和人工审核后组装、版本化、冻结的正式题集。

## 推荐文件

```text
legal_questions_draft.jsonl
legal_questions_draft.errors.jsonl
legal_questions_draft.jsonl.metadata.json
```

## 运行前定义变量

```powershell
$repo = "C:\llm-eval"
$dataset = "$repo\methodology\01_造Benchmark\legal\data\datasets\<dataset_id>"
Set-Location $repo
```

## 运行候选题生成

```powershell
py -m methodology.02_构建题集.legal.generation.generate `
  --input "$dataset\extract\legal_cases_extract.jsonl" `
  --output "$dataset\drafts\legal_questions_draft.jsonl" `
  --questions-per-case 2
```

实际 CLI 参数：

- `--input`：extract 阶段案件 JSONL，必填。
- `--output`：候选题 JSONL，必填；相邻 metadata 和 errors 由程序写出。
- `--questions-per-case N`：每案生成 N 道候选题。
- `--cases case_id_1,case_id_2`：只处理指定的逗号分隔 `case_id`，适合定向试跑。
- `--max-items N`：只处理前 N 个案件，适合 smoke；它只限制本次运行，不应决定正式文件名。

例如，单案试跑必须使用独立输出：

```powershell
$smoke = Join-Path $env:TEMP "legal-generation-smoke"
New-Item -ItemType Directory -Force -Path $smoke | Out-Null

py -m methodology.02_构建题集.legal.generation.generate `
  --input "$dataset\extract\legal_cases_extract.jsonl" `
  --output (Join-Path $smoke "legal_questions_draft_smoke_1.jsonl") `
  --max-items 1 `
  --questions-per-case 2
```

候选题生成可以独立启动，不要求重新运行 clean 或 extract；只要输入 JSONL 满足 extract 数据契约即可。
