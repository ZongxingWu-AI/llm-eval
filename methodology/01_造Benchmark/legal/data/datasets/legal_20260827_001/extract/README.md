# extract：法律信息提取

## 1. 这一步做什么

`extract` 读取 clean 案件，重点处理 `sections.court_reasoning` 和 `sections.judgment`，生成可用于出题的 `legal_extraction`。它同时保留 clean 的全文、章节、来源和分类字段，因此下游可以继续审计原文。

## 2. 输入和输出

输入：`$dataset\clean\legal_cases_clean.jsonl`。

正式输出：

```text
$dataset\extract\legal_cases_extract.jsonl
$dataset\extract\legal_cases_extract.jsonl.metadata.json
```

每行继承 clean 案件字段，并增加 `legal_extraction`；`quality.extraction` 记录该条案件实际采用的提取方法和错误。

## 3. 运行前定义通用变量

```powershell
$repo = "C:\llm-eval"
$dataset = "$repo\methodology\01_造Benchmark\legal\data\datasets\<dataset_id>"
Set-Location $repo
```

## 4. 规则运行（默认，不调用模型）

```powershell
py -m methodology.01_造Benchmark.legal.extraction.extract `
  --input "$dataset\clean\legal_cases_clean.jsonl" `
  --output "$dataset\extract\legal_cases_extract.jsonl"
```

不传 `--use-llm` 时，使用可重复的规则提取；输出可直接作为后续生成阶段的输入。

## 5. 单条 LLM smoke

下面的试跑使用独立临时输出，不覆盖正式规则版 extract。API key 只从环境变量或 `.env` 读取，不写入命令和 README。

```powershell
$smoke = Join-Path $env:TEMP "llm-eval-extract-llm-smoke"
New-Item -ItemType Directory -Force -Path $smoke | Out-Null
$env:EXTRACTOR_BASE_URL = "https://llm-center.modelbest.cn/v1"

py -m methodology.01_造Benchmark.legal.extraction.extract `
  --input "$dataset\clean\legal_cases_clean.jsonl" `
  --output (Join-Path $smoke "legal_cases_extract_llm_smoke_1.jsonl") `
  --max-items 1 `
  --use-llm
```

## 6. 完整批次 LLM 运行

下面的命令直接处理 clean 阶段的整批数据，并将真实模型结果写入显式指定的正式 extract 输出；命令会覆盖该输出文件及相邻 metadata。

```powershell
$env:EXTRACTOR_BASE_URL = "https://llm-center.modelbest.cn/v1"

py -m methodology.01_造Benchmark.legal.extraction.extract `
  --input "$dataset\clean\legal_cases_clean.jsonl" `
  --output "$dataset\extract\legal_cases_extract.jsonl" `
  --use-llm `
  --workers 4 `
  --qps 3
```

如果只是试跑或想和规则版比较，请改用临时目录和独立文件，不要让 smoke 输出覆盖正式文件。

## 7. 并发和 QPS 限流

旧版本的 `run()` 会逐条调用 `extract_case()`，因此模型请求是串行的。
传入 `--use-llm` 时，extract 会使用线程池批量调用模型；不传该参数时仍只执行规则提取。

| 参数 | 默认值 | 含义 |
|---|---:|---|
| `--workers` | `4` | 同时处理的最大案件数；传 1 可恢复串行 |
| `--qps` | `3` | 当前进程每秒最多启动的模型请求数；首次请求和重试都受限流控制 |

并发不会改变结果契约：所有案件处理完成后统一写出，JSONL 顺序仍与 clean 输入顺序一致；某条模型请求失败时，该案仍按原有逻辑保留规则提取结果，并在 `quality.extraction.errors` 中记录原因。

规则运行不需要模型并发，但 metadata 仍会记录本次命令的 `workers` 和 `qps` 参数，便于复现。

## 8. 输出字段和降级逻辑

### 8.1 继承 clean 的字段

`case_id`、`source`、`document`、`parties`、`full_text`、`anonymized_text`、`sections`、`facts_summary`、`cited_statutes`、`amounts`、`dates`、`interest_expressions`、`classification`、`quality` 原样保留；extract 可能更新 `classification.legal_issues`，并在 `quality` 下增加 `extraction`。

### 8.2 `legal_extraction`

| 字段 | 含义 |
|---|---|
| `legal_issues` | 模型或规则识别出的法律争议焦点，字符串数组 |
| `evidence_findings` | 法院对证据、举证和证明力的判断，带来源定位的对象数组 |
| `conclusions` | 法院说理和判决主文中的裁判结论，带来源定位的对象数组 |

`evidence_findings` 和 `conclusions` 的每个元素通常包含：

| 字段 | 含义 |
|---|---|
| `conclusion` | 对证据判断或裁判结论的文本表达 |
| `source_section` | 来源章节名，如 `court_reasoning` 或 `judgment` |
| `source_quote` | 可在对应章节直接查到的原文短引 |

### 8.3 `quality.extraction`

| 字段 | 含义 |
|---|---|
| `version` | 提取器版本，如 `legal-extractor-v1` |
| `method` | 该案件实际采用的方法：`rules` 或 `llm_grounded` |
| `status` | 当前质量状态；默认 `needs_review`，表示仍建议复核 |
| `errors` | 模型调用、JSON 解析或引用过滤等问题；规则正常运行时可为空 |

`deterministic_extract(case)` 是规则底座：先按句号、问号、感叹号、分号或换行切句，再按关键词识别争议、证据和结论。`extract_case(case, client, model)` 先得到规则结果；没有客户端时直接使用规则结果；有客户端时尝试模型提取；模型结果 JSON 合法且来源章节、短引可回查时才使用 `llm_grounded`，否则保留规则结果并在 `errors` 记录原因。也就是说，`--use-llm` 表示“尝试调用模型”，不保证每条结果都来自模型。

`_valid_grounded_items()` 是来源定位闸门：模型声称引用的章节不存在，或 `source_quote` 不在该章节原文中，该条模型项会被丢弃，避免不可验证的答案依据进入下游。

## 9. 批次 metadata

`legal_cases_extract.jsonl.metadata.json` 描述一次批量运行，而不是替代逐条质量字段：

| 字段 | 含义 |
|---|---|
| `track` | `legal_benchmark.extraction` |
| `started_at` | 本次运行开始时间 |
| `input`、`output` | 实际 clean 输入和 extract 输出路径 |
| `count` | 实际输出案件数 |
| `method` | 按逐条结果汇总：全 rules=`rules`，全 LLM=`llm_grounded`，两者并存=`mixed`，空批次=`none` |
| `method_counts` | 各方法数量，如 `{ "rules": 49, "llm_grounded": 1 }` |
| `model` | 启用 LLM 时的模型名；规则运行可为空 |
| `workers` | 本次运行使用的最大工作线程数 |
| `qps` | 本次运行使用的模型请求启动速率上限 |

## 10. 模型地址

代码使用 OpenAI 兼容客户端的 `client.chat.completions.create(...)`，因此 `EXTRACTOR_BASE_URL` 应是 API 根地址：

```text
https://llm-center.modelbest.cn/v1
```

客户端会自动追加 `/chat/completions`。模型名从 `EXTRACTOR_MODEL` 读取。
