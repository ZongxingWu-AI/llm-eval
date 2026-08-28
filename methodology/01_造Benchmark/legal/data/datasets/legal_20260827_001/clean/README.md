# clean：无损解析和初步结构化

## 1. 这一步做什么

`clean` 对一个批次 `raw/` 中的案件做确定性解析：保留全文，按标题或规则切出章节，再从原文派生案号、当事人、法条、金额、日期、分类和质量状态。它不调用大模型，因此同一输入重复运行应得到可解释、可复现的结果。

## 2. 输入和输出

输入是 `$dataset\raw` 中的原始案件文件；输出是：

```text
$dataset\clean\legal_cases_clean.jsonl
$dataset\clean\legal_cases_clean.jsonl.metadata.json
$dataset\manifests\legal_sources.jsonl
```

JSONL 一行是一案，不是一道题。字段含义、嵌套结构和字段来源见下方字段表；`source.sha256` 用于把结果回查到 raw 原文。

## 3. 运行前定义通用变量

```powershell
$repo = "C:\llm-eval"
$dataset = "$repo\methodology\01_造Benchmark\legal\data\datasets\<dataset_id>"
Set-Location $repo
```

## 4. 正式或完整批次运行

```powershell
py -m methodology.01_造Benchmark.legal.ingestion.clean `
  --raw-dir "$dataset\raw" `
  --output "$dataset\clean\legal_cases_clean.jsonl" `
  --manifest-output "$dataset\manifests\legal_sources.jsonl"
```

`--raw-dir`、`--output` 和 `--manifest-output` 都应显式指定。换批次时只修改 `$dataset`，不修改代码。

## 5. 单条 smoke 试跑

试跑必须使用独立输出，不能覆盖正式 clean 或来源清单：

```powershell
$smoke = Join-Path $env:TEMP "llm-eval-clean-smoke"
New-Item -ItemType Directory -Force -Path $smoke | Out-Null

py -m methodology.01_造Benchmark.legal.ingestion.clean `
  --raw-dir "$dataset\raw" `
  --output (Join-Path $smoke "legal_cases_clean_smoke_1.jsonl") `
  --manifest-output (Join-Path $smoke "legal_sources_smoke_1.jsonl") `
  --max-items 1
```

## 6. 案件记录字段

每行是一个案件对象。字段来源分为三类：

- **原文保留字段**：直接保存原始案件内容，便于回查；
- **规则派生字段**：由 clean 的确定性解析函数从原文中提取或归类；
- **追踪字段**：用于把案件结果关联回原始文件。

### 顶层字段

| 字段 | 来源 | 含义 |
|---|---|---|
| `case_id` | 追踪 | 根据原文指纹生成的稳定案件标识；用于跨 clean、extract 和后续题目阶段关联同一案件 |
| `source` | 追踪/派生 | 原始文件、相对路径、SHA-256、来源地址和获取时间等信息 |
| `document` | 规则派生 | 文书身份信息，如案号、法院、裁判日期、文书类型和程序阶段 |
| `parties` | 规则派生 | 从文书正文识别出的原告、被告、第三人等主体及其角色 |
| `full_text` | 原文保留 | 清洗后保留的完整案件文本，是后续回查的主文本 |
| `anonymized_text` | 原文保留/可选 | 如果输入已提供匿名化文本，则保留对应版本；没有时可以为空 |
| `sections` | 原文保留/规则切分 | 按案件标题切出的章节文本，如诉讼请求、事实、法院理由和判决主文 |
| `facts_summary` | 规则派生 | 根据事实章节形成的初步摘要；不是最终法律结论 |
| `cited_statutes` | 规则派生 | 在正文中按规则识别出的被引用法律、法规或条文名称 |
| `amounts` | 规则派生 | 从文本中识别出的金额及其上下文，不等于法院最终支持金额 |
| `dates` | 规则派生 | 从文本中识别出的日期及其上下文 |
| `interest_expressions` | 规则派生 | 与利息、逾期利息、利率或起算时间相关的原文表达 |
| `classification` | 规则派生 | 案件类别、案由路径、程序标签和证据标签等初步分类 |
| `quality` | 运行/规则派生 | 解析版本、处理时间、审核状态、解析状态和缺失章节 |

### 重要嵌套字段

| 路径 | 含义 |
|---|---|
| `source.file_name` / `source.relative_path` | 当前批次 raw 中的文件定位信息 |
| `source.sha256` | 当前原始文本的内容指纹；原文变化时通常会变化 |
| `document.case_no` | 案件案号 |
| `document.court` | 审理法院 |
| `document.judgment_date` | 裁判日期 |
| `document.document_type` | 文书类型，如民事判决书 |
| `document.procedure_stage` | 程序阶段，如一审、二审 |
| `sections.claims` | 诉讼请求部分 |
| `sections.defenses` | 被告答辩或抗辩部分 |
| `sections.facts` | 经审理查明的事实部分 |
| `sections.court_reasoning` | 法院说理部分，通常是 extract 的重点输入 |
| `sections.judgment` | 判决主文部分，通常用于确认裁判结论 |
| `classification.primary_category` | 初步主类别 |
| `classification.cause_path` | 初步案由路径 |
| `classification.legal_issues` | clean 阶段预留的法律问题标签，通常为空，后续由 extract 补充 |
| `classification.procedure_tags` | 程序相关标签 |
| `classification.evidence_tags` | 证据相关标签 |
| `quality.parser_version` | clean 解析器版本 |
| `quality.status` | `parsed` 或 `needs_review` 等案件级状态 |
| `quality.missing_sections` | 未识别到的关键章节 |

## 7. 运行级 metadata

相邻的 `legal_cases_clean.jsonl.metadata.json` 是一次运行的记录，不是一条案件记录。它与 JSONL 的区别是：JSONL 记录“处理出了什么”，metadata 记录“这次程序是怎么跑的”。

| 字段 | 含义 |
|---|---|
| `track` | 处理阶段标识，当前为 `legal_benchmark.ingestion` |
| `started_at` | 本次运行开始时间，通常使用带时区的 ISO 时间 |
| `input` | 实际读取的 raw 目录路径 |
| `output` | 实际写出的 clean JSONL 路径 |
| `manifest_output` | 实际写出的来源清单路径 |
| `count` | 本次实际处理并写出的案件数 |
| `method` | 处理方式；clean 当前使用规则解析，通常为 `rules` |
| `parser_version` | 本次使用的解析器版本，如 `legal-parser-v3` |
| `status` | 产物状态，如正式生成、迁移既有产物或试跑 |

metadata 主要用于审计、输入输出路径核对、数量检查、方法和版本确认、复现与排错，也可供未来的自动化验证使用。当前下游业务阶段主要读取 clean JSONL，不把 metadata 当作案件内容输入。
