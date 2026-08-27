# releases：冻结后的正式题集

## 目录职责

保存经过人工审核、组装并冻结的正式 Benchmark 题集。`release` 是供验证和评测使用的稳定输入，不应直接由模型生成步骤覆盖。

## 推荐产物

```text
legal_questions_release_v1.jsonl
legal_questions_release_v1.rejected.jsonl
legal_release_manifest_v1.json
```

其中，`v1` 表示发布版本；它与案例数量无关。manifest 记录输入草稿、输出摘要、题目数量和内容哈希。

## 运行

```powershell
python -m methodology.02_构建题集.legal.dataset.build `
  --input "<dataset>/drafts/legal_questions_draft.jsonl" `
  --output "<dataset>/releases/legal_questions_release_v1.jsonl" `
  --manifest-output "<dataset>/releases/legal_release_manifest_v1.json"
```

只有通过审核的题目才应进入 release；需要开发试跑时才使用 `--include-pending`。

## 下游

```text
releases/legal_questions_release_v1.jsonl
  → validation/校验结果
  → evaluation/评测运行目录
```
