# Pairwise Judge 运行结果目录

## 1. 目录用途

本目录保存开放题 LLM-as-Judge 的逐题裁判结果、偏见统计、报告和运行元数据。

## 2. 数据来源

输入来自 `tracks/pairwise_judge/data/judge_answers.jsonl`，裁判模型进行两轮位置交换比较，最多可以启用三个裁判。

## 3. 文件命名规则

常见文件包括：

```text
pairwise_results.jsonl
bias_stats.json
judge_report.md
run_metadata.json
```

## 4. 字段说明

| 字段 | 含义 |
|---|---|
| `id` | 开放题编号。 |
| `judge_winner` 或 `final_winner` | 映射回原始选手后的胜者。 |
| `round1_winner` | 第一轮在原始位置下的胜者。 |
| `round2_winner` | 第二轮交换位置后、映射回原始选手的胜者。 |
| `position_bias` | 两轮结论冲突时是否标记位置偏见。 |
| `score_a_total` | 原始选手 A 的裁判总分。 |
| `score_b_total` | 原始选手 B 的裁判总分。 |
| `judge1_winner`、`judge2_winner`、`judge3_winner` | 不同裁判的最终判断。 |
| `reason_1` | 第一轮裁判分析。 |
| `reason_2` | 第二轮裁判分析。 |
| `error` | 裁判输出解析或调用错误。 |

## 5. 示例

```json
{"id":"q01","round1_winner":"A","round2_winner":"A","final_winner":"A","position_bias":false,"score_a_total":8,"score_b_total":7,"error":""}
```

## 6. 统计解释

- 两轮都支持同一个原始选手：可以形成稳定胜者；
- 两轮交换后结论冲突：记录 `position_bias=true`；
- 多裁判没有严格多数：`final_winner` 为 `tie`；
- 偏见统计在所有有效逐题结果上汇总，不把错误调用当成胜负。

## 7. 是否提交 Git

除本 README 外，运行结果默认被 `.gitignore` 忽略。
