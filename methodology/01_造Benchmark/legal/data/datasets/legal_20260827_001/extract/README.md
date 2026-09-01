# extract：案件事实地图的二次结构化层

## 1. 阶段定位

`extract` 接收 clean 生成的脱敏案件，建立可回查的 canonical `case_fact_map`。它不是简单的关键词清洗，也不是评测维度分类；它把完整案件组织成后续出题可以引用的法律事实层。

在数据使用契约中，事实地图按“领域确认后的案件结构化结果”使用。当前工程实现可以由 LLM 完成预抽取并由规则校验来源，但没有独立专家审核平台，因此不能伪造具体专家姓名或逐条审核日志。

## 2. Canonical 事实地图

生产 `legal_extraction` 只保留一个事实地图对象：

```json
{
  "case_fact_map": {
    "key_facts": [],
    "party_relationships": [],
    "claims": [],
    "defenses": [],
    "disputed_issues": [],
    "evidence": [],
    "court_found_facts": [],
    "procedural_timeline": [],
    "applied_laws": [],
    "court_reasoning": [],
    "judgment_results": []
  }
}
```

每个条目都必须包含：

```json
{
  "text": "结构化内容",
  "source_quote": "脱敏后的连续原文片段",
  "source_quote_sha256": "..."
}
```

生产链路不再输出或消费以下旧字段：

```text
legal_issues
evidence_findings
conclusions
```

旧信息分别归入 `disputed_issues`、`evidence`、`court_reasoning`、`court_found_facts` 和 `judgment_results`。

## 3. 抽取状态

只有完整 LLM 事实地图通过字段、类型、逐字引用和本地哈希生成校验，才允许进入出题：

```text
method = llm_grounded
review_status = ready_for_generation
```

模型调用失败、JSON 不完整、引用无法回查或结果混入旧字段时：

```text
method = rules_fallback
review_status = needs_review
```

规则 fallback 仅用于排查和后续人工修正，默认不得进入正式 generation，也不能标记为 `expert_confirmed`。只有未来存在真实人工确认记录时，才可以使用 `expert_confirmed`。

不采用“LLM 缺什么再用规则静默补什么”的混合方式：LLM 全量通过就使用完整 LLM 版本，否则整体进入 `needs_review`。

## 4. 长案件处理

长案件按以下顺序处理：

```text
external_text
→ 分块抽取
→ 事实地图合并与去重
→ 时间线排序
→ 连续原文引用校验
→ 抽取状态门禁
```

所有外部模型请求只使用脱敏材料，不读取 `full_text`。

## 5. 运行示例

```powershell
$repo = "C:\llm-eval"
$dataset = "$repo\methodology\01_造Benchmark\legal\data\datasets\<dataset_id>"
Set-Location $repo

py -m methodology.01_造Benchmark.legal.extraction.extract `
  --input "$dataset\clean\legal_cases_clean.jsonl" `
  --output "$dataset\extract\legal_cases_extract.jsonl" `
  --use-llm `
  --workers 1 `
  --qps 1
```

当前环境需要预先安装并配置 OpenAI 兼容客户端；没有客户端时不要把规则结果误认为已经完成 LLM 抽取。

## 6. 与出题阶段的关系

```text
extract：事实地图决定“案件中有哪些可验证材料”
generation：维度和题型决定“想测什么、怎么测”
validation：独立 Reviewer 决定候选题是否合格
```

事实地图不是评测维度。预测题在 generation 阶段会建立安全视图，排除 `court_found_facts`、`court_reasoning` 和 `judgment_results`，避免把最终裁判结论泄露给被测模型。
