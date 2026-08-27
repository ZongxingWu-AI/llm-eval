# raw：当前批次原始案件

本目录保存当前数据集批次的原始判决书，一案一文件，支持 `.md` 和 `.txt`。本批次当前包含 50 份案件。

原始文件不应在进入 `raw/` 前被摘要替代或删除法院说理、判决主文等内容。`clean.py` 会根据全文生成 `case_id` 和 SHA-256，并在同一批次的 `manifests/legal_sources.jsonl` 记录来源。

运行入口：

```powershell
python -m methodology.01_造Benchmark.legal.ingestion.clean `
  --raw-dir "<dataset>/raw" `
  --output "<dataset>/clean/legal_cases_clean.jsonl" `
  --manifest-output "<dataset>/manifests/legal_sources.jsonl"
```
