# clean：原文保存、脱敏与稳定元数据

## 1. 阶段职责

`clean` 是 01「造 Benchmark」的确定性预处理阶段，不调用大模型。它负责：

- 在本地受控结果中完整保存原始 `full_text`，用于审计和回查；
- 生成同案内占位符稳定的脱敏全文 `external_text`；
- 提取案号、主体、日期、金额、法条、利息和初步分类等稳定元数据；
- 记录案件级 `case_id`、原始内容 `source.sha256` 和质量状态。

`clean` 不负责法律事实总结，不做规则章节划分，也不生成案件事实摘要。正式事实地图由后续 `extract` 阶段建立。

## 2. 输入和输出

输入：

```text
$dataset\raw
```

输出：

```text
$dataset\clean\legal_cases_clean.jsonl
$dataset\clean\legal_cases_clean.jsonl.metadata.json
$dataset\manifests\legal_sources.jsonl
```

## 3. 文本安全分层

| 字段 | 用途 |
|---|---|
| `full_text` | 仅限本地受控保存和审计，保留原始全文，禁止发送外部模型 |
| `external_text` | 唯一允许进入 extract、generation 和其他外部模型调用的脱敏全文 |

clean 不输出 `sections`、`external_sections`、`facts_summary`，也不输出依赖章节划分的 `quality.missing_sections`。这样可以避免不稳定的规则章节标签成为后续接口依赖。

脱敏后的主体在同一案件内保持稳定，例如：

```text
原告甲、被告乙、公司一、地址一、手机号一、身份证号一
```

不同案件之间不复用真实身份映射。

## 4. 运行命令

```powershell
$repo = "C:\llm-eval"
$dataset = "$repo\methodology\01_造Benchmark\legal\data\datasets\<dataset_id>"
Set-Location $repo

py -m methodology.01_造Benchmark.legal.ingestion.clean `
  --raw-dir "$dataset\raw" `
  --output "$dataset\clean\legal_cases_clean.jsonl" `
  --manifest-output "$dataset\manifests\legal_sources.jsonl"
```

## 5. 产物契约

每行是一案，保留以下业务字段：

```text
case_id
source
document
parties
classification
cited_statutes
amounts
dates
interest_expressions
full_text
external_text
quality
```

其中：

- `source.sha256` 和 `case_id` 由原始文件内容计算，不能由脱敏文本替代；
- `external_text` 是后续外部模型的唯一原文来源；
- `classification` 只保存案件分类和标签，不承载事实总结；
- `quality` 记录解析和审查状态，不再记录章节缺失状态。

## 6. 与后续阶段的关系

```text
raw
→ clean：full_text + external_text + 稳定元数据
→ extract：只读取 external_text，建立 case_fact_map
→ generation：只使用脱敏材料和事实地图出题
```

`full_text` 永远只在本地受控保存和审计范围内使用。任何 `source_quote` 都必须由后续程序在完整 `external_text` 中逐字连续回查。
