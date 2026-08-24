# Pairwise Judge Prompt 模板目录

## 1. 目录用途

本目录保存开放题回答生成和裁判比较使用的 Prompt 模板。

## 2. Prompt 文件说明

裁判模板至少需要理解以下输入：

| 内容 | 含义 |
|---|---|
| `question` | 开放题题目。 |
| `answer_a` | 当前裁判位置 A 的回答。 |
| `answer_b` | 当前裁判位置 B 的回答。 |
| 评分维度 | 裁判判断回答质量时使用的标准。 |

## 3. 两轮位置交换

第一轮把原始 A 放在裁判位置 A，把原始 B 放在裁判位置 B。

第二轮把原始 B 放在裁判位置 A，把原始 A 放在裁判位置 B。

因此第二轮模型返回的 A/B 标签必须映射回原始选手后才能统计胜者。

## 4. 示例输入

```json
{"question":"解释什么是大模型评测。","answer_a":"回答一","answer_b":"回答二"}
```

## 5. 上游和下游

模板由 `judge_prompt.py` 和 `pairwise.py` 加载，输出交给公共 JSON 解析器 `core.json_utils`。

## 6. 是否提交 Git

Prompt 模板应提交 Git。修改后应重新运行 Pairwise Judge 的位置交换和偏见统计测试。
