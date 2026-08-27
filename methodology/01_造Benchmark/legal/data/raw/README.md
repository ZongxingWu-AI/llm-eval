# 法律原始案例目录

## 目录用途

`raw/` 是一个批次内部的原始输入目录，保存真实民事一审判决书原文。正式批次位于 `data/datasets/<dataset_id>/raw/`；旧的 `data/raw/` 仅保留用户已有资料，不作为默认输入。

## 文件命名规则

一案一文件，支持 `.md` 和 `.txt`。文件名可保留原始案号，例如：

```text
（2024）浙0483民初5218号.md
```

不要在放入 raw 前手动截断、摘要或删除法院说理和判决主文。

## 来源清单

运行 `clean.py` 时由命令行指定 manifest 输出路径，例如：

```text
<dataset>/manifests/legal_sources.jsonl
```

主要字段如下：

| 字段 | 含义 |
|---|---|
| `case_id` | 根据全文内容生成的案件标识。 |
| `source_file` | 批次 raw 中的原始文件名。 |
| `sha256` | 原文内容的 SHA-256；内容改变后哈希也会改变。 |
| `source_url` | 原始来源网址，未知时为空。 |
| `retrieved_at` | 获取时间，未知时为空。 |
| `reuse_status` | 复用状态；`local_only` 表示只在本地使用。 |
| `review_status` | 来源和质量审核状态。 |

## 上游和下游

```text
批次 raw/ → clean/legal_cases_clean.jsonl → extract/
```

原始判决书通常被 `.gitignore` 忽略。未经来源、隐私、脱敏和质量审核的原文不得进入公开 release。
