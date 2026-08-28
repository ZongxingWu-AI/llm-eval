# 法律 Benchmark 数据批次

## 批次定位

本目录代表一个独立的数据集批次。批次目录名是 `<dataset_id>`，用于隔离本批次的原始案件、阶段结果、来源追踪和题集产物；它不编码案例数量。

创建新批次时，复制目录结构并使用新的 `<dataset_id>`，不要覆盖已有批次：

```text
<dataset_id>/
├── raw/        # 原始案件
├── clean/      # 无损解析和初步结构化
├── extract/    # 法律信息提取
├── manifests/  # 来源和选择追踪
├── drafts/     # 候选题草稿
└── releases/   # 审核冻结的正式题集
```

验证和评测通常写入独立的运行目录，不直接污染案件批次：

```text
<run_dir>/
└── validation/ 或 evaluation/
```

## 批次内数据流

```text
raw → clean → extract → drafts → releases → validation → evaluation
```

- `raw` 是下游所有结果的原始依据，不在原文件中回写派生字段。
- `clean` 和 `extract` 是案件级 JSONL；每行通过 `case_id` 连接。
- `manifests` 保存来源、入批选择和集合级关系。
- `drafts` 保存尚未审核通过的候选题；`releases` 保存可供验证和评测的冻结题集。
- 原始内容通过 `source.sha256` 追踪，运行过程通过 `.metadata.json` 和 manifest 追踪。

## 运行约定

各阶段可以独立运行，具体路径由命令行显式传入。通用变量和完整命令模板见：

```text
methodology/01_造Benchmark/legal/data/README.md
```

打开各阶段目录下的 README，可以直接对照该目录中的 JSONL、metadata 或 manifest 字段。
