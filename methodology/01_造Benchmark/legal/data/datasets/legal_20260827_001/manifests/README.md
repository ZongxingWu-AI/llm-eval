# manifests：法律数据来源与阶段清单

## 目录职责

保存本批次的来源登记、案例选择记录和阶段报告。manifest 是“这批数据从哪里来、包含哪些案例、生成了什么”的运行级索引，不替代案件 JSONL 本身。

## 文件

- `legal_sources.jsonl`：由 `clean.py` 生成，一行一个原始案例，记录 `case_id`、`source_file`、`sha256`、来源和审核状态。
- `legal_cases_selection.jsonl`：案例选择阶段的记录，保存选择原因和案例身份。
- `legal_cases_selection_report.md`：对选择范围、数量和质量情况的可读摘要。

## 追踪关系

`legal_sources.jsonl` 的 `source_file` 应能在同一批次的 `raw/` 中找到；`case_id` 应与 `clean/legal_cases_clean.jsonl` 和 `extract/legal_cases_extract.jsonl` 对齐。`sha256` 用来检测原文是否被替换或修改。

## 运行

来源清单由以下命令写入，输出路径必须由本次批次命令显式指定：

```powershell
python -m methodology.01_造Benchmark.legal.ingestion.clean `
  --raw-dir "<dataset>/raw" `
  --output "<dataset>/clean/legal_cases_clean.jsonl" `
  --manifest-output "<dataset>/manifests/legal_sources.jsonl"
```

后续批次使用新的 `data/datasets/<dataset_id>/`，不修改本目录说明，也不把案例数量写入文件名。
