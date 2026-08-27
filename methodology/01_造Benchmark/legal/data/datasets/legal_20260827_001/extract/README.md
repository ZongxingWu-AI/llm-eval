# extract：法律案件结构化提取产物

## 目录职责

`extract/` 保存 `extraction.extract` 从 `clean/` 案件中提取的法律争议、证据判断和法院结论。它保留原始全文、章节和来源定位，并增加 `legal_extraction` 与 `quality.extraction`。

当前产物：

```text
legal_cases_extract.jsonl
legal_cases_extract.jsonl.metadata.json
```

`source_section` 和 `source_quote` 必须能回查到案件对应章节；规则提取和模型提取的方式记录在 `quality.extraction.method` 中。

## 运行

```powershell
python -m methodology.01_造Benchmark.legal.extraction.extract `
  --input "<dataset>/clean/legal_cases_clean.jsonl" `
  --output "<dataset>/extract/legal_cases_extract.jsonl" `
  --use-llm
```

不传 `--use-llm` 时使用可重复的规则提取；启用模型时，单案失败会回退规则结果并继续处理。

## 下游

```text
../clean/legal_cases_clean.jsonl
  → extraction.extract
  → legal_cases_extract.jsonl
  → generation.generate
```
