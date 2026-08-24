# C-Eval 数据目录

## 1. 目录用途

本目录保存 C-Eval 客观题的输入数据。评测模块从这里读取题目，调用被测模型后，将逐题结果写入 `../results/`。

## 2. 数据来源

题目可以来自 Hugging Face 数据集下载，也可以来自经过格式转换的本地 JSONL。当前示例文件是 `ceval_computer_network.jsonl`。

## 3. 文件命名规则

推荐使用：

```text
ceval_<subject>.jsonl
```

例如：

```text
ceval_computer_network.jsonl
```

## 4. JSON/JSONL 文件说明

JSONL 文件每一行是一个独立题目对象，不是一个大 JSON 数组。程序会逐行读取，所以一行损坏时能够定位到具体题目。

## 5. 字段说明

| 字段 | 含义 |
|---|---|
| `id` | 题目唯一编号，例如 `computer_network-0000`。 |
| `subject` | 科目名称，例如 `computer_network`。 |
| `question` | 题干文本。 |
| `A`、`B`、`C`、`D` | 四个选项的文本。 |
| `answer` | 标准答案，通常是 `A`、`B`、`C` 或 `D`。 |

## 6. 示例

```json
{"id":"computer_network-0000","subject":"computer_network","question":"题干","A":"选项一","B":"选项二","C":"选项三","D":"选项四","answer":"C"}
```

模型只接收题干和选项，标准答案只用于评测后比较，不应放进发送给模型的 Prompt。

## 7. 上游和下游

```text
fetch.py 下载/整理题目
    ↓
ceval/data/*.jsonl
    ↓
evaluate.py 调用模型并评分
    ↓
ceval/results/
```

## 8. 是否提交 Git

示例题目和不含敏感信息的固定数据可以提交。运行结果不放在本目录，而是写入 `results/`。
