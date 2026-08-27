# 01 造 Benchmark 模块地图

| 小类 | 实际文件 | 输入 | 输出 | 是否调用模型 |
|---|---|---|---|---|
| 原始文本无损解析 | `methodology/01_造Benchmark/legal/ingestion/clean.py` | `<dataset>/raw/*.md` 或 `.txt` | `<dataset>/clean/legal_cases_clean.jsonl` + manifest | 否 |
| 法律信息提取 | `methodology/01_造Benchmark/legal/extraction/extract.py` | clean JSONL | `<dataset>/extract/legal_cases_extract.jsonl` + metadata | 仅 `--use-llm` |
| 分类和 Schema | `methodology/01_造Benchmark/legal/taxonomy`、`schemas` | 受控词表和结构约束 | 供解析、出题、校验使用 | 否 |
| 来源和质量管理 | clean/extract 内的 source、quality、manifest、metadata | raw 和案件结果 | manifests 与相邻元数据 | 否 |

所有 `<dataset>` 都由命令行显式指定；`paths.py` 只登记法律项目根路径和 `DATASETS_ROOT`，不绑定某个批次。

完整数据流：

```text
raw → clean → extract → drafts → releases → validation → evaluation
```
