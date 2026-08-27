# drafts：候选题草稿

## 目录职责

保存从本批次 `extract/legal_cases_extract.jsonl` 生成、尚未正式发布的候选题。候选题默认带有 `review_status=pending`，需要人工审核后才能进入 `releases/`。

## 推荐产物

```text
legal_questions_draft.jsonl
legal_questions_draft.errors.jsonl
legal_questions_draft.jsonl.metadata.json
```

错误记录和元数据与候选题文件保持同一输出前缀，方便追踪输入路径、处理数量、模型和生成方法。

## 运行

```powershell
python -m methodology.02_构建题集.legal.generation.generate `
  --input "<dataset>/extract/legal_cases_extract.jsonl" `
  --output "<dataset>/drafts/legal_questions_draft.jsonl" `
  --questions-per-case 2
```

试跑时可使用 `--max-items 1`，但必须把 `--output` 指向单独的临时文件，不能覆盖正式草稿。

## 质量要求

每道题都应包含 `case_id`、`source_evidence` 和可回查的 `source_quote`。候选题只能引用 extract 案件实际保留的章节文本。
