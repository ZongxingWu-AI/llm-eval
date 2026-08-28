# 02 构建题集模块地图：法律 Benchmark

| 模块 | 实际文件 | 输入 | 输出 | 关键职责 |
|---|---|---|---|---|
| 维度配置 | `methodology/02_构建题集/legal/config/dimension_catalog.json` | 九类维度、上下文策略和评分口径 | 维度目录、Prompt 路由 | 定义测什么、给什么材料、如何评分 |
| 题集蓝图 | `methodology/02_构建题集/legal/config/dataset_blueprint.json` | 维度、案件类别、难度和风险配额 | 配额约束和覆盖统计 | 决定正式 release 如何平衡组装 |
| 配置加载 | `methodology/02_构建题集/legal/config/__init__.py` | dimension catalog | 可查询的维度配置 | 校验 ID 唯一、任务映射和分布 |
| 统一出题引擎 | `methodology/02_构建题集/legal/generation/generate.py` | extract JSONL：全文、sections、法律事实地图 | `drafts/legal_questions_draft.jsonl`、errors、metadata | 按 `dimension_id` 选择 Prompt，生成候选题 |
| 维度 Prompt | `methodology/02_构建题集/legal/prompts/dimensions/*.md` | 完整案件材料和该维度规则 | 供出题模型使用的模板 | 指定问题形式、必答点、Rubric 和禁泄露内容 |
| 正式题集组装 | `methodology/02_构建题集/legal/dataset/build.py` | approved 候选题、蓝图 | `releases/legal_questions_release_v1.jsonl`、rejected、manifest、coverage | 按维度配额组装，保留案件级 split |
| 案件级 split | `methodology/02_构建题集/legal/dataset/split.py` | release 中的 `case_id` | dev/calibration/test 标签 | 防止同案事实跨集合泄漏 |
| 质量校验 | `methodology/02_构建题集/legal/validation/validate.py` | release + extract 案件 + 可选蓝图 | validation JSONL、Markdown、metadata | 检查契约、证据定位、答案泄露、可作答性和配额 |

### `context_type` 与材料策略

| context_type | 03 传给被测模型的材料 |
|---|---|
| `self_contained` | 题目专门整理的必要背景 + question |
| `source_excerpt` | 可定位的原文片段/案件材料 + question |
| `full_document` | 完整案件材料 + question |
| `scenario` | 风险场景描述 + question |

`reference_answer`、`rubric`、`source_evidence` 只供 04 和人工校验使用，不属于被测模型输入。`judgment_prediction` 不得把法院最终裁判结论放入 context。

九类 dimension_id 为：`fact_extraction`、`issue_identification`、`rule_application`、`evidence_evaluation`、`judgment_prediction`、`legal_argument`、`amount_calculation`、`compliance_refusal`、`procedure_time_reasoning`。
