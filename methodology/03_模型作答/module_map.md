# 03 模型作答模块地图：法律 Benchmark

| 模块 | 实际文件 | 输入 | 输出 | 是否评分 |
|---|---|---|---|---|
| 被测模型调用 | `methodology/03_模型作答/legal/evaluation/run.py` | release、contestant 配置、`context + question` | 原始回答记录 | 否 |
| 上下文组装 | `methodology/03_模型作答/legal/evaluation/run.py` | `context_type`、`context`、`question` | 发给 contestant 的单题输入 | 否 |
| 原始回答落盘 | `methodology/03_模型作答/legal/evaluation/run.py` + `core/data_io.py` | 模型响应和调用元数据 | `legal_model_outputs.jsonl`、`legal_model_errors.jsonl`、`run_metadata.json` | 否 |
| 下游边界 | `methodology/04_结果评测/legal/scoring/run.py` | release + 原始回答 | 评分结果、报告、Excel | 是，但不属于 03 |

03 只保留原始事实：模型实际收到了什么、返回了什么、耗时多少、用了多少 token。`question_id` 是后续 04 与正式 release 的唯一关联键。
