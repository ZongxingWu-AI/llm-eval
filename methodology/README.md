# 法律 Benchmark 教学总索引

本仓库把“评测一个法律大模型/法律问答系统”拆成四个有明确边界的阶段：

```text
01 造 Benchmark → 02 构建题集 → 03 模型作答 → 04 结果评测
```

目标是形成按能力维度可解释的模型画像，而不是把事实理解、规则适用、金额计算和安全拒答混成一个分数。

## 四个目录

- `01_造Benchmark`：管理真实判决书，完成 `raw → clean → extract`，保留全文和来源证据。
- `02_构建题集`：以九类法律维度为顶层覆盖单位，使用统一出题引擎、维度 Prompt 和题集蓝图生成、审核、组装和校验题目。
- `03_模型作答`：读取冻结 release，按 `context_type` 给被测模型提供材料和问题，只保存原始回答。
- `04_结果评测`：读取同一 release 和原始回答，独立执行规则评分、红线评分或 Rubric Judge，输出 PASS/REVIEW/REJECT、分维度报告和 Excel。

## 数据流

```text
raw
→ clean
→ extract
→ drafts
→ releases
→ validation
→ legal_model_outputs
→ legal_evaluation_results
```

## 九类法律评测维度

```text
事实抽取、争议焦点识别、法律规则适用、证据评价、
裁判结果预测、法律论证、金额计算、合规拒答、程序与时间推理
```

每个维度在 `methodology/02_构建题集/legal/config/dimension_catalog.json` 中定义任务类型、二级推理能力、适用案件类型、目标题量、上下文策略、评分方式、难度/风险分布和 Prompt 模板。题集蓝图按维度配额组装 release，因此一个案件不要求覆盖全部维度，也不为每个维度复制一套 Python 流程。

## 批次数据

正式数据统一位于 `methodology/01_造Benchmark/legal/data/datasets/<dataset_id>/`。批次内部使用 `raw/`、`clean/`、`extract/`、`manifests/`、`drafts/` 和 `releases/`；验证和评测通常写入独立运行目录，不污染案件批次。公共基础层位于 `core/`。
