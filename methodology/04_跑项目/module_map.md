# 04 跑项目模块地图：法律 Benchmark

| 小类 | 实际文件 | 输入 | 输出 |
|---|---|---|---|
| 批量法律评测 | ``methodology/04_跑项目/legal/evaluation/run.py`` | releases JSONL | legal results JSONL |
| 结果记录 | ``methodology/04_跑项目/legal/evaluation/run.py`` + ``core/data_io.py`` | 逐题回答和评分 | errors、metadata |
| 报告和导出 | ``methodology/04_跑项目/legal/evaluation/run.py`` + ``methodology/04_跑项目/legal/evaluation/excel_export.py`` | 运行结果 | Markdown 报告和 Excel |
