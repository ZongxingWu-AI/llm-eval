# 04 跑项目学习顺序：法律 Benchmark

1. 先用 5 道已校验题做工程联调。
2. 检查模型回答、评分路由、错误记录、延迟、Token 和报告。
3. 在 calibration 集完成人工对照后，再只运行冻结的 test split。
4. 结果只写入法律项目自己的 ``methodology/01_造Benchmark/legal/results`` 目录。
