# 法律原始案例目录

## 1. 目录用途

保存真实民事一审判决书原文，作为法律 Benchmark 的唯一原始输入。

## 2. 数据来源

文件可以来自公开裁判文书、用户本地整理材料或经过授权的内部资料。每份文书都应尽量记录来源网址、获取时间和复用状态。

## 3. 文件命名规则

一案一文件，支持 `.md` 和 `.txt`。文件名建议保留原始案号，例如：

```text
（2024）浙0483民初5218号.md
```

不要在放入 raw 前手动截断、摘要或删除法院说理和判决主文。

## 4. 来源清单

清洗程序会在 `../manifests/raw_manifest.jsonl` 生成来源清单。主要字段如下：

| 字段 | 含义 |
|---|---|
| `case_id` | 根据全文内容生成的案件标识。 |
| `source_file` | 本地原始文件名。 |
| `sha256` | 原文 UTF-8 内容的 SHA-256。内容改变后哈希也会改变。 |
| `source_url` | 原始来源网址，未知时为空。 |
| `retrieved_at` | 获取时间，未知时为空。 |
| `reuse_status` | 复用状态；`local_only` 表示只在本地使用。 |
| `review_status` | 来源和质量审核状态。 |

## 5. 示例

```json
{"case_id":"case_0001","source_file":"（2024）浙0483民初5218号.md","sha256":"...","source_url":"","retrieved_at":"","reuse_status":"local_only","review_status":"pending"}
```

## 6. 上游和下游

```text
本目录原文
    ↓
python -m tracks.legal_benchmark.ingestion.clean
    ↓
data/parsed/
```

## 7. 是否提交 Git

除本 README 外，本目录所有判决书都被 `.gitignore` 忽略。未经来源、隐私、脱敏和质量审核的原文不得进入公开 release。
