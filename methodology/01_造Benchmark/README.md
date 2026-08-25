# 01 造 Benchmark：法律真实案例

## 解决的问题

确定法律 Benchmark 的范围、数据来源和结构化字段，把本地判决书无损转换为后续出题可以读取的案件对象。

## 代码和产出

- ``methodology/01_造Benchmark/legal/ingestion/clean.py``：raw → parsed。
- ``methodology/01_造Benchmark/legal/extraction/extract.py``：parsed → cleaned。
- ``methodology/01_造Benchmark/legal/taxonomy``：受控分类标签。
- ``methodology/01_造Benchmark/legal/schemas``：字段约束。

本环节不修改 raw 原文；使用 ``--use-llm`` 的结构化提取步骤才会调用模型。
