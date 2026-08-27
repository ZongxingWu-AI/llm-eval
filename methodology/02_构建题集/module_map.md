# 02 构建题集模块地图：法律 Benchmark

| 小类 | 实际文件 | 输入 | 输出 |
|---|---|---|---|
| 候选题生成 | `methodology/02_构建题集/legal/generation/generate.py` | `<dataset>/extract/legal_cases_extract.jsonl` | `<dataset>/drafts/legal_questions_draft.jsonl` + errors + metadata |
| 正式题集组装 | `methodology/02_构建题集/legal/dataset/build.py` | `<dataset>/drafts/legal_questions_draft.jsonl` | `<dataset>/releases/legal_questions_release_v1.jsonl` + manifest |
| 案件级 split | `methodology/02_构建题集/legal/dataset/split.py` | release 中的 `case_id` | dev/calibration/test |
| 质量校验 | `methodology/02_构建题集/legal/validation/validate.py` | release + extract cases | validation JSONL + Markdown 报告 |

具体 `<dataset>` 路径由命令行指定，文件名不编码案例数量。
