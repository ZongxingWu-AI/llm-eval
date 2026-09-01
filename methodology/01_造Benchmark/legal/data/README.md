# 法律 Benchmark 数据目录规范

## 1. 目录定位

法律 Benchmark 的数据按**批次**隔离，不把案例数量写进目录名或文件名。每个批次使用一个独立的 `<dataset_id>`：

```text
data/
└── datasets/
    └── <dataset_id>/
        ├── raw/
        ├── clean/
        ├── extract/
        ├── manifests/
        ├── drafts/
        └── releases/
```

批次 ID 只用于区分一次数据集，不代表案例数量。以后新增 51 条、100 条或完全不同的一批案件，只需创建新的 `<dataset_id>`，再通过命令行传入该批次路径。

## 2. 统一命令变量

下面的变量是 PowerShell 示例中的通用占位约定。请把 `<dataset_id>` 替换为实际批次目录名；不要把试跑输出写回正式结果文件。

```powershell
$repo = "C:\llm-eval"
$dataset = "$repo\methodology\01_造Benchmark\legal\data\datasets\<dataset_id>"
```

- `$repo`：仓库根目录。
- `$dataset`：本次处理的一个批次根目录；换批次时只修改这一行。
- 每个阶段都可以独立运行，但必须用命令行显式指定输入和输出。
- `--max-items` 只能限制试跑数量，不能替代正式输出文件命名。
- 试跑应使用 `$env:TEMP` 下的独立目录或其他临时路径，避免覆盖正式批次。

## 3. 数据流

```text
raw → clean → extract → drafts → releases → validation → evaluation
```

| 阶段 | 作用 | 典型结果 |
|---|---|---|
| `raw` | 保存原始案件文件，作为不可变审计底稿 | 一案一份 `.md` |
| `clean` | 不调用大模型，保存原文、生成脱敏全文并提取稳定规则元数据 | `legal_cases_clean.jsonl` |
| `extract` | 从 clean 案件提取争议、证据判断和裁判结论 | `legal_cases_extract.jsonl` |
| `manifests` | 记录来源、选择和批次级追踪信息 | `legal_sources.jsonl`、选择记录、报告 |
| `drafts` | 保存模型生成但尚未发布的候选题 | `legal_questions_draft.jsonl` |
| `releases` | 保存审核后冻结的正式题集 | `legal_questions_release_v1.jsonl` |
| `validation` | 对题集结构、标签、证据和案件关系做校验 | 独立验证 JSONL |
| `evaluation` | 调用被测模型并记录逐题评测结果 | 独立运行目录 |

## 4. 路径和追踪原则

- `paths.py` 只登记法律项目根目录；具体批次路径必须由 CLI 的 `--input`、`--output`、`--manifest-output` 等参数指定。
- JSONL 保存案件或题目的业务数据；相邻 `.metadata.json` 保存一次运行的输入、输出、数量、方法、模型和状态等运行信息。
- manifest 保存来源、选样和集合关系；它不是某一步处理逻辑的替代品。
- `case_id` 是案件级稳定身份；`source.sha256` 是原始内容指纹。
- 任何 `source_quote` 都应能在案件的脱敏全文 `external_text` 中逐字连续回查；最终哈希 `source_quote_sha256` 由本地程序生成，正式接口不再保存 `source_section`。
- 每个批次、每个阶段都应放置 README，说明本阶段文件、字段、字段来源、上下游和运行方式。

## 5. 旧目录

`data/raw/` 可以保留用户已有的历史资料，但不是批次链路的默认入口。正式运行统一使用 `data/datasets/<dataset_id>/...`。
