# 法律 Benchmark 数据总目录

## 1. 目录用途

本目录保存法律真实案例 Benchmark 的数据生命周期文件。法律线按以下顺序流转：

```text
raw → parsed → cleaned → drafts → releases → evaluation/results
```

## 2. 子目录说明

| 子目录 | 用途 | 是否默认提交 |
|---|---|---|
| `raw/` | 原始判决书，只在本地保存。 | 否 |
| `parsed/` | 无损解析结果。 | 否 |
| `cleaned/` | 结构化提取结果。 | 否 |
| `drafts/` | 候选题和人工审核工作区。 | 否 |
| `manifests/` | 来源、发布和校验清单。 | 是，需审核 |
| `releases/` | 经审核的正式题集。 | 是，需审核 |

## 3. JSON/JSONL 说明

JSONL 文件每一行是一个案例、题目或清单记录；JSON 文件通常是一个发布清单、taxonomy 或一次运行的整体元数据。

## 4. 数据状态

- `pending`：尚未完成人工审核；
- `approved`：人工审核通过，可以进入正式题集；
- `local_only`：来源只保存在本地，不代表可以公开发布；
- `parsed`：解析器认为主要章节已识别；
- `needs_review`：存在缺失章节或需要人工确认。

## 5. 上游和下游

每一阶段都应保留上游文件路径、case_id、SHA-256 和处理版本，确保同一案件可以追溯和重复处理。
