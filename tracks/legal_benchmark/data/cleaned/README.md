# 法律 cleaned 数据目录

## 1. 目录用途

保存 extraction 阶段生成的结构化案件。这里可以同时包含规则提取结果和带来源定位的模型提取结果。

## 2. 数据来源和文件命名

输入来自 `../parsed/`，默认输出为：

```text
structured_cases.jsonl
```

## 3. JSONL 文件说明

每一行对应一个案件。原始解析字段会保留，并新增 `legal_extraction`。

## 4. 重点字段说明

| 字段 | 含义 |
|---|---|
| `legal_extraction` | 结构化法律提取结果。 |
| `legal_extraction.legal_issues` | 法律争议焦点或问题描述。 |
| `legal_extraction.evidence_findings` | 证据评价结果。 |
| `legal_extraction.conclusions` | 法院结论或规则结论。 |
| `source_section` | 结论来源章节，例如 `court_reasoning` 或 `judgment`。 |
| `source_quote` | 能在来源章节中原样找到的证据短句。 |
| `quality.extraction` | 提取器版本、规则/模型方法和错误信息。 |

## 5. 示例

```json
{"legal_extraction":{"conclusions":[{"conclusion":"法院确认尚欠货款","source_section":"court_reasoning","source_quote":"法院确认尚欠货款"}]}}
```

`source_quote` 必须是对应章节中的真实子串，否则该条模型结论不会进入有效结果。

## 6. 上游和下游

```text
parsed/parsed_judgments.jsonl
    ↓
extraction.extract
    ↓
cleaned/structured_cases.jsonl
    ↓
generation.generate
```

## 7. 是否提交 Git

除本 README 外默认不提交。正式发布只使用经过审核和脱敏的字段。
