# 法律 Benchmark Prompt 模板目录

## 1. 目录用途

本目录保存法律结构化提取、候选题生成、Rubric 评分和语义校验使用的 Prompt 模板。

## 2. 模板和输入

| 模板 | 主要输入 |
|---|---|
| `legal_extraction_prompt.md` | `case_sections`，即案件各章节文本。 |
| `legal_generation_prompt.md` | 案件分类、事实、法院说理、判决主文和来源证据。 |
| `legal_scorer_rubric.md` | 题目、参考答案、Rubric 和模型回答。 |
| `legal_validator_prompt.md` | 题目、来源证据和结构化案件。 |

## 3. 输出约束

模型输出应优先使用 JSON。所有结论需要带：

```text
source_section
source_quote
```

其中 `source_quote` 必须能在相应章节中找到。不能定位的模型结果由代码过滤。

## 4. 示例

```json
{"case_sections":{"court_reasoning":"本院认为..."},"source_quote":"本院认为...","reference_answer":"..."}
```

## 5. 上游和下游

模板由 `core.prompt_loader` 加载，法律线各阶段填充变量后调用 `core.llm_client`。解析模型输出统一使用 `core.json_utils`。

## 6. 是否提交 Git

Prompt 模板属于可复现配置，应提交 Git；原始判决全文不写入模板文件。
