# 法律 parsed 数据目录

## 1. 目录用途

保存 ingestion 阶段对 raw 判决书进行无损分段后的中间 JSONL。该阶段只做确定性解析，不让摘要替代全文。

## 2. 数据来源和文件命名

输入来自 `../raw_selected_50/`，默认输出为：

```text
parsed_judgments_selected_50.jsonl
```

试跑文件可以使用带有案例名的 JSONL 文件，但仍应保留 `case_id` 和 `source.sha256`。

## 3. JSONL 文件说明

每一行对应一份判决书案件对象。

## 4. 字段说明

| 字段 | 含义 |
|---|---|
| `case_id` | 基于原文 SHA-256 前缀生成的案件 ID。 |
| `source` | 文件名、来源 URL、SHA-256、获取时间和复用状态。 |
| `document` | 案号、法院、裁判日期、文书类型和审级。 |
| `parties` | 所有识别出的原告、被告、第三人、代理人等。 |
| `full_text` | 完整判决书原文，不能被摘要替代。 |
| `anonymized_text` | 对识别出的姓名做基础替换后的文本，仅作辅助。 |
| `sections` | `header`、`claims`、`defenses`、`facts`、`evidence`、`court_reasoning`、`judgment`、`tail` 等章节。 |
| `facts_summary` | 从事实章节派生的摘要，不是全文。 |
| `cited_statutes` | 识别到的法条表达列表。 |
| `amounts` | 金额表达列表。 |
| `dates` | 日期表达列表。 |
| `interest_expressions` | 利息、利率和迟延履行利息相关表达。 |
| `classification` | 民事领域、审级、文书类型、案由和程序/证据标签。 |
| `quality` | parser version、处理时间、缺失章节和审核状态。 |

## 5. 示例

```json
{"case_id":"case_0001","document":{"case_no":"（2024）浙0483民初5218号","procedure_stage":"一审"},"parties":[{"role":"原告","name":"王某"}],"full_text":"完整原文...","sections":{"claims":"诉讼请求...","court_reasoning":"本院认为...","judgment":"判决如下..."},"quality":{"status":"parsed","missing_sections":[]}}
```

## 6. 上游和下游

下游 `extraction.extract` 会读取 `sections` 和 `full_text`，生成 `cleaned/structured_cases.jsonl`。

## 7. 是否提交 Git

除本 README 外默认不提交。该目录内容可以由 raw 重新生成。
