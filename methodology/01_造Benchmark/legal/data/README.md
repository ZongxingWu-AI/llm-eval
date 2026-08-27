# 法律 Benchmark 数据目录

## 按批次组织

所有正式数据集都放在 `data/datasets/<dataset_id>/` 下。当前批次为：

```text
data/datasets/legal_20260827_001/
├── raw/
├── clean/
├── extract/
├── manifests/
├── drafts/
├── releases/
└── README.md
```

`legal_20260827_001` 是批次 ID：日期表示创建日期，`001` 表示批次序号，不表示案例数。后续 51 条、100 条或另一批数据，只需新建批次目录并在命令行替换路径。

## 数据流

```text
raw
  → clean
  → extract
  → drafts
  → releases
  → validation
  → evaluation
```

- `raw/`：一案一文件的原始判决书，不修改原文。
- `clean/`：无损解析后的案件 JSONL，例如 `legal_cases_clean.jsonl`。
- `extract/`：提取法律争议、证据和结论后的案件 JSONL，例如 `legal_cases_extract.jsonl`。
- `manifests/`：来源、选择和运行清单。
- `drafts/`：待人工审核的候选题。
- `releases/`：冻结后供验证和评测的正式题集。

## 路径约定

代码只在 `paths.py` 集中登记法律项目根路径；具体批次和文件路径不写死在代码中，统一通过 CLI 的 `--input`、`--output` 和相关参数传入。`--max-items` 只是试跑限制，不决定文件名。

## 追踪与验证

案件级追踪使用 `case_id` 和 `source.sha256`；运行级追踪使用相邻的 metadata 和 manifests。每个引用证据都应通过 `source_section`、`source_quote` 回查原文；validation 阶段检查结构、来源和一致性。

旧的 `data/raw/` 保留供用户已有资料使用，但不属于当前正式批次，也不作为命令默认输入。
