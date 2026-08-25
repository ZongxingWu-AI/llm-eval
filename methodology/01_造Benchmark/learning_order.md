# 01 造 Benchmark 学习顺序

本阶段只学习法律真实案例 Benchmark 的数据构造，不运行外部项目代码。

1. 阅读 ``legal/taxonomy/taxonomy.json``、``legal/schemas/question.schema.json`` 和数据目录 README。
2. 阅读 ``methodology/01_造Benchmark/legal/ingestion/clean.py``，先用 1 个 raw 案例运行无损解析。
3. 检查 ``full_text``、``sections``、``parties``、``classification`` 和 ``quality``。
4. 阅读 ``methodology/01_造Benchmark/legal/extraction/extract.py``，先运行规则提取，再用 1 案比较 ``--use-llm``。
5. 确认 ``source_section`` 与 ``source_quote`` 可回溯后，再进入构建题集。
