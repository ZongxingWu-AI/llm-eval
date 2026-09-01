# 已废弃：法律候选题生成 Prompt

本文件保留仅用于历史说明，不再作为当前法律题集生成流程的 Prompt。

当前流程不再消费旧版 `legal_extraction.legal_issues`、`legal_extraction.evidence_findings` 或 `legal_extraction.conclusions` 字段，也不再要求候选题把完整背景和问题拼接到单一 `question` 字段中。

当前出题入口是统一引擎：

```text
methodology/02_构建题集/legal/generation/generate.py
```

当前出题模型使用：

```text
methodology/02_构建题集/legal/prompts/dimensions/
methodology/02_构建题集/legal/prompts/formats/
```

出题输入以脱敏的 canonical `case_fact_map` 为事实来源，并由 `dimension_id` 与 `question_format` 共同决定测试目标和题面形式。生成结果必须经过规则校验、来源校验、可作答性校验和独立 Reviewer 审题后，才能进入正式题集。

当前 canonical 事实地图包含：

```text
key_facts
party_relationships
claims
defenses
disputed_issues
evidence
court_found_facts
procedural_timeline
applied_laws
court_reasoning
judgment_results
```

如需运行当前流程，请使用 02 阶段的 CLI，而不是本文件。
