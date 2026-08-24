# Pairwise Judge 数据目录

## 1. 目录用途

本目录保存开放题问题和两个选手模型的回答。`generate_answers.py` 读取问题并生成回答，`evaluate.py` 再读取回答交给裁判模型比较。

## 2. 数据来源

问题来自人工编写或业务样本；回答由 `CONTESTANT_A` 和 `CONTESTANT_B` 配置的模型生成。

## 3. 文件命名规则

常见文件包括：

```text
judge_questions.jsonl
judge_answers.jsonl
```

## 4. JSONL 文件说明

每一行是一个独立问题或一组回答。`id` 用于把问题和回答关联起来。

## 5. 字段说明

### judge_questions.jsonl

| 字段 | 含义 |
|---|---|
| `id` | 问题唯一编号。 |
| `question` | 给两个选手回答的开放题题目。 |

### judge_answers.jsonl

| 字段 | 含义 |
|---|---|
| `id` | 与问题文件对应的编号。 |
| `question` | 原始题目，便于结果自包含。 |
| `answer_a` | 原始选手 A 的回答。 |
| `answer_b` | 原始选手 B 的回答。 |
| `model_a` | 生成 `answer_a` 的模型名。 |
| `model_b` | 生成 `answer_b` 的模型名。 |
| `error` | 回答生成错误；空字符串表示成功。 |

## 6. 示例

```json
{"id":"q01","question":"介绍大模型评测。","answer_a":"回答A","answer_b":"回答B","model_a":"model-a","model_b":"model-b","error":""}
```

注意：A/B 表示原始选手身份，不表示裁判第二轮中的位置。第二轮会交换两个回答的位置。

## 7. 上游和下游

```text
judge_questions.jsonl
    ↓
generate_answers.py
    ↓
judge_answers.jsonl
    ↓
evaluate.py
    ↓
pairwise_judge/results/
```

## 8. 是否提交 Git

不含敏感信息的示例问题和回答可以提交。运行结果不写回本目录。
