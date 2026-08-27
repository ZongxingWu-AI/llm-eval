# clean：法律案件无损解析产物

## 目录职责

`clean/` 保存 `ingestion.clean` 的确定性解析结果。它从同一批次的 `raw/` 读取判决书，保留 `full_text` 和 `sections`，并增加案号、当事人、分类、哈希及质量状态。不调用大模型。

当前产物：

```text
legal_cases_clean.jsonl
```

每行对应一个案件，不是一道题。案件对象内部仍保留 `source`、`document`、`parties`、`full_text`、`sections` 和 `quality` 等字段。

## 运行

```powershell
python -m methodology.01_造Benchmark.legal.ingestion.clean `
  --raw-dir "<dataset>/raw" `
  --output "<dataset>/clean/legal_cases_clean.jsonl" `
  --manifest-output "<dataset>/manifests/legal_sources.jsonl"
```

`--max-items` 仅用于试跑；试跑时必须把结果写到另一个明确命名的文件。

## 可追溯性

每条记录通过 `case_id` 和 `source.sha256` 回到原始文件；来源清单位于同一批次的 `manifests/legal_sources.jsonl`；metadata 记录输入、输出、数量、解析方法和版本。`full_text` 是审计底稿，不能用摘要替代。

