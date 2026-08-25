# 04 跑项目：法律 Benchmark 批量评测

本环节读取正式 release 题集，调用被测模型，交给法律评分器，最后写出逐题结果、错误、报告、运行元数据和可选 Excel。
唯一主要入口是 ``methodology/04_跑项目/legal/evaluation/run.py``；它会自动调用 ``legal_scorer.py``。
