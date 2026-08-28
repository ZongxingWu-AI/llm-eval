# evaluation：法律 Benchmark 模型作答

## 阶段职责

`run.py` 读取已经冻结的 release 题集，调用被测模型并保存原始回答。它不执行评分，也不初始化 JUDGE；评分由 04 结果评测阶段读取原始回答后独立完成。

## 通用运行模板

```powershell
$repo = "C:\llm-eval"
$dataset = "$repo\methodology\01_造Benchmark\legal\data\datasets\<dataset_id>"
$runDir = Join-Path $env:TEMP "legal-model-answer-run"
Set-Location $repo

py -m methodology.03_模型作答.legal.evaluation.run `
  --input "$dataset\releases\legal_questions_release_v1.jsonl" `
  --output $runDir
```

实际参数：

- `--input`：正式题集 JSONL，必填。
- `--output`：本次回答运行目录；不指定时程序会创建时间戳目录，但推荐显式指定。
- `--max-items N`：只调用前 N 道题，用于 smoke；试跑使用新的 `$runDir`。

输出只包含 `legal_model_outputs.jsonl`、`legal_model_errors.jsonl` 和 `run_metadata.json`。不要把原始回答写入 `releases/` 的正式题集文件。
