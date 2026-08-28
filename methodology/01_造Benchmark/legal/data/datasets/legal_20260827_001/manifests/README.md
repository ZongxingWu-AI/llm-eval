# manifests：来源与批次清单

`manifests/` 是批次级和案件级的追踪目录，不是一个需要单独启动的处理阶段。它回答“这批数据中的案件对应哪些原始文件”，而 clean/extract JSONL 回答“案件解析和提取出了什么”。

## `legal_sources.jsonl`：案件级来源清单

该文件由 clean 阶段生成，一行对应一个案件：

| 字段 | 含义 |
|---|---|
| `case_id` | 与 clean、extract 记录对齐的案件 ID |
| `source_file` | 当前批次 `raw/` 中的原始文件名 |
| `sha256` | 原始文本内容的 SHA-256 指纹 |
| `source_url` | 原始来源地址；本地资料可以为空 |
| `retrieved_at` | 文件获取或登记时间 |
| `reuse_status` | 来源是否可复用等状态 |
| `review_status` | 来源或解析清单的审核状态 |

它的主要用途是把 clean/extract 中的一条案件结果回查到当前批次的 raw 原文，并检查原文是否被替换。若要重新生成它，重新运行 clean 并显式指定 `--manifest-output`。

## 当前批次的边界

当前批次不保留独立的选样阶段产物；正式链路从当前批次的 `raw/` 开始：

```text
raw/
  → clean/legal_cases_clean.jsonl
  → manifests/legal_sources.jsonl
  → extract/legal_cases_extract.jsonl
```

因此，`manifests/` 中的 `legal_sources.jsonl` 是当前正式链路的一部分；它不是题目数据，也不替代 clean 或 extract 的业务 JSONL。

## 与 metadata 的区别

| 文件类型 | 主要回答的问题 | 粒度 |
|---|---|---|
| `legal_sources.jsonl` | 这条案件来自哪个 raw 文件？原文指纹是什么？ | 一案一行 |
| `clean/*.metadata.json` | clean 这次使用什么输入、输出、解析器和数量？ | 一次运行 |
| `extract/*.metadata.json` | extract 这次使用什么输入、输出、模型/规则和数量？ | 一次运行 |
| clean/extract 业务 JSONL | 这条案件具体解析或提取出了什么？ | 一案一行 |

## 运行边界

manifests 本身没有必须单独执行的 CLI。需要重新生成来源清单时，使用 clean 命令：

```powershell
$repo = "C:\llm-eval"
$dataset = "$repo\methodology\01_造Benchmark\legal\data\datasets\<dataset_id>"
Set-Location $repo

py -m methodology.01_造Benchmark.legal.ingestion.clean `
  --raw-dir "$dataset\raw" `
  --output "$dataset\clean\legal_cases_clean.jsonl" `
  --manifest-output "$dataset\manifests\legal_sources.jsonl"
```

运行时应使用新的批次目录和明确的输出路径，避免覆盖已有正式产物。
