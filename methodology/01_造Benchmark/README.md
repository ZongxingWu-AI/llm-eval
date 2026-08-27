# 01 造 Benchmark：法律真实案例

## 解决的问题

确定法律 Benchmark 的范围、数据来源和结构化字段，把本地判决书无损转换为后续出题可以读取的案件对象。

## 代码和产出

- `methodology/01_造Benchmark/legal/ingestion/clean.py`：`raw → clean`，不调用大模型。
- `methodology/01_造Benchmark/legal/extraction/extract.py`：`clean → extract`，默认规则提取，可选 `--use-llm`。
- `methodology/01_造Benchmark/legal/taxonomy`：受控分类标签。
- `methodology/01_造Benchmark/legal/schemas`：字段结构约束。

## 批次运行

数据位于 `legal/data/datasets/<dataset_id>/`。例如：

```powershell
python -m methodology.01_造Benchmark.legal.ingestion.clean `
  --raw-dir "<dataset>/raw" `
  --output "<dataset>/clean/legal_cases_clean.jsonl" `
  --manifest-output "<dataset>/manifests/legal_sources.jsonl"

python -m methodology.01_造Benchmark.legal.extraction.extract `
  --input "<dataset>/clean/legal_cases_clean.jsonl" `
  --output "<dataset>/extract/legal_cases_extract.jsonl"
```

所有具体路径由命令行指定，因此同一套代码可以复用于任意数量的案例和任意批次。`case_id` 与 `source.sha256` 负责案件级追踪，metadata 和 manifest 负责运行级追踪。
