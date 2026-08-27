# 法律真实案例 Benchmark

本仓库按“造 Benchmark → 构建题集 → 当裁判 → 跑项目”组织法律评测流程。核心数据链路是：

```text
raw → clean → extract → drafts → releases → validation → evaluation
```

## 快速入口

- `methodology/01_造Benchmark/legal/ingestion/clean.py`：不调用模型，把 raw 判决书无损解析为 clean 案件 JSONL。
- `methodology/01_造Benchmark/legal/extraction/extract.py`：从 clean 案件提取法律信息；可选 `--use-llm`。
- `methodology/02_构建题集/legal/generation/generate.py`：从 extract 案件生成待审核候选题。
- `methodology/02_构建题集/legal/dataset/build.py`：把审核通过的候选题组装成 release。
- `methodology/02_构建题集/legal/validation/validate.py`：验证题集结构、来源证据和案件一致性。
- `methodology/04_跑项目/legal/evaluation/run.py`：使用环境变量中的模型配置执行评测。

## 数据批次

正式数据按批次放在：

```text
methodology/01_造Benchmark/legal/data/datasets/<dataset_id>/
```

当前已迁移的批次是 `legal_20260827_001`。批次 ID 中的日期是创建日期，序号不是案例数量；文件名也不编码数量。因此新增 51 条、100 条或另一批案例时，只需创建新的批次目录，并在命令行指定对应路径。

## 第一、二步示例

```powershell
python -m methodology.01_造Benchmark.legal.ingestion.clean `
  --raw-dir ".../data/datasets/legal_20260827_001/raw" `
  --output ".../data/datasets/legal_20260827_001/clean/legal_cases_clean.jsonl" `
  --manifest-output ".../data/datasets/legal_20260827_001/manifests/legal_sources.jsonl"

python -m methodology.01_造Benchmark.legal.extraction.extract `
  --input ".../data/datasets/legal_20260827_001/clean/legal_cases_clean.jsonl" `
  --output ".../data/datasets/legal_20260827_001/extract/legal_cases_extract.jsonl" `
  --use-llm
```

所有与具体数据集有关的输入输出路径都由命令行传入；`--max-items` 只是试跑限制，不能代替输出文件命名。案件级追踪依赖 `case_id`、`source.sha256`，运行级追踪依赖 metadata 和 manifest。

## 其他目录

- `core/`：公共数据读写、模型客户端、Prompt 和运行元数据工具。
- `学习文档/`：学习笔记和面试复习材料。
- `tests/`：法律链路的契约、manifest、CLI 和生成逻辑测试。
