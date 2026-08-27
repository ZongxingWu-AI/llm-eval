# 当前数据集批次：legal_20260827_001

## 批次说明

这是 2026 年 8 月 27 日建立的第 001 个法律数据集批次，当前包含 50 份原始判决书。`001` 是批次序号，不是数量编码；后续数据集应创建新的批次目录。

## 流水线

```text
raw/
  → clean/legal_cases_clean.jsonl
  → extract/legal_cases_extract.jsonl
  → drafts/legal_questions_draft.jsonl
  → releases/legal_questions_release_v1.jsonl
  → validation
  → evaluation/results
```

各阶段可以独立运行，输入和输出路径由命令行显式指定。案件 JSON 的 `case_id`、`source.sha256` 和来源 manifest 用于跨阶段追踪。
