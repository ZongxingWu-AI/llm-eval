# 法律 Benchmark Taxonomy 目录

## 1. 目录用途

保存法律案件级和问题级分类的受控词表，防止不同案例使用同义但不一致的标签。

## 2. 文件说明

当前主要文件：

```text
taxonomy.json
```

## 3. 主要字段

| 字段 | 含义 |
|---|---|
| `domains` | 案件横向领域，例如 `民事`。 |
| `procedure_stages` | 审级，例如 `一审`。 |
| `document_types` | 文书类型，例如 `判决书`。 |
| `primary_categories` | 五个第一版法律方向。 |
| `cause_tree` | 一级方向到具体案由的受控树。 |
| `task_types` | 问题任务类型。 |
| `answer_types` | 答案形式。 |
| `scoring_methods` | `rule`、`redline`、`rubric_judge`。 |
| `difficulties` | `easy`、`medium`、`hard`。 |
| `risk_levels` | `low`、`medium`、`high`。 |
| `procedure_tags` | 程序特征标签。 |
| `evidence_tags` | 证据特征标签。 |

## 4. 示例

```json
{"primary_categories":["合同、准合同纠纷"],"cause_tree":{"合同、准合同纠纷":["买卖合同纠纷"]},"scoring_methods":["rule","redline","rubric_judge"]}
```

## 5. 上游和下游

解析器负责生成初步案由，题目生成和正式题集校验必须从本词表取值。

## 6. 是否提交 Git

Taxonomy 是可复现数据契约，应提交 Git。新增标签时要同步增加测试、README 和必要的人工审核规则。
