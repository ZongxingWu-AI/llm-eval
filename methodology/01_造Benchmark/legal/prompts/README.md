# 法律 Benchmark Prompt 模板目录

## 当前生效模板

| 模板 | 阶段 | 用途 |
|---|---|---|
| `legal_extraction_prompt.md` | 01 造 Benchmark | 从完整脱敏案件材料抽取 canonical `case_fact_map` |
| `legal_validator_prompt.md` | 02 构建题集 | 由独立 Reviewer 审查候选题 |
| `legal_scorer_rubric.md` | 04 结果评测 | 为 Rubric Judge 提供评分规则 |

02 阶段出题使用统一引擎加载：

```text
methodology/02_构建题集/legal/prompts/dimensions/
methodology/02_构建题集/legal/prompts/formats/
```

维度 Prompt 决定测试目标，题型 Prompt 决定题面形式；二者都只能使用脱敏的 canonical `case_fact_map` 和可回查来源。

## 已废弃模板

```text
legal_generation_prompt.md
```

该文件仅保留历史说明，不是当前出题入口，也不应被代码或人工运行继续使用。旧版 `legal_issues`、`evidence_findings`、`conclusions` 不再是生产数据契约。

## 共同安全约束

- 外部模型只能接收 `external_text` 和脱敏事实地图。
- `full_text` 只限本地受控审计，禁止外发。
- `source_quote` 必须来自脱敏文本并能逐字回查。
- 03 模型作答不接收 `reference_answer`、`rubric`、`source_evidence` 或正确选项。
- 生成题目必须经过规则校验、可作答性校验和独立 Reviewer 审题。
