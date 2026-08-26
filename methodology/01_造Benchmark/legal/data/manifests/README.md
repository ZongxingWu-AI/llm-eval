# 法律 manifests 清单目录

## 1. 目录用途

保存原始来源、正式发布和质量校验清单。清单不替代原文或题集，而是记录它们如何产生、是否审核和是否可追溯。

## 2. 文件说明

| 文件 | 作用 |
|---|---|
| `raw_selected_50_manifest.jsonl` | 每份本地原始判决书一条记录。 |
| `release_manifest.json` | 一次正式题集发布的版本、数量和来源摘要。 |
| `validation_report.jsonl` | 每道题的校验状态和问题。 |

## 3. 字段说明

| 字段 | 含义 |
|---|---|
| `case_id` | 案件唯一标识。 |
| `source_file` | 本地来源文件名。 |
| `sha256` | 原文内容哈希。 |
| `source_url` | 来源地址。 |
| `retrieved_at` | 获取时间。 |
| `reuse_status` | 复用限制，例如 `local_only`。 |
| `review_status` | 人工审核状态。 |
| `parser_version` | 处理该数据的解析器版本。 |
| `validation_status` | 校验结果，例如 `passed` 或 `failed`；不同校验文件也可能使用 `status` 表示同一概念。 |

## 4. 示例

```json
{"case_id":"case_0001","source_file":"case.md","sha256":"...","source_url":"","retrieved_at":"","reuse_status":"local_only","review_status":"pending"}
```

## 5. 是否提交 Git

manifest 不包含原始全文，经过审核后可以提交，用于复现和追溯。
