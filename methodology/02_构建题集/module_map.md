# 02 构建题集模块地图：法律 Benchmark

| 小类 | 实际文件 | 输入 | 输出 |
|---|---|---|---|
| 候选题生成 | ``methodology/02_构建题集/legal/generation/generate.py`` | cleaned JSONL | drafts JSONL |
| 正式题集组装 | ``methodology/02_构建题集/legal/dataset/build.py`` | approved 候选题 | releases JSONL + manifest |
| 案件级 split | ``methodology/02_构建题集/legal/dataset/split.py`` | case_id | dev/calibration/test |
| 质量校验 | ``methodology/02_构建题集/legal/validation/validate.py`` | release + cleaned cases | validation report |
