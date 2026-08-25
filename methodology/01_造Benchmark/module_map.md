# 01 造 Benchmark 模块地图

| 小类 | 实际文件 | 输入 | 输出 | 是否调用模型 |
|---|---|---|---|---|
| 原始文本无损解析 | ``methodology/01_造Benchmark/legal/ingestion/clean.py`` | ``legal/data/raw*/*.md`` | ``legal/data/parsed/*.jsonl`` | 否 |
| 法律信息提取 | ``methodology/01_造Benchmark/legal/extraction/extract.py`` | parsed JSONL | ``legal/data/cleaned/*.jsonl`` | 仅 ``--use-llm`` |
| 分类和 Schema | ``methodology/01_造Benchmark/legal/taxonomy``、``schemas`` | 受控词表和结构约束 | 供解析、出题、校验使用 | 否 |
| 来源和质量管理 | clean/extract 内的 manifest、quality 字段 | raw 和解析结果 | manifests、quality | 否 |
