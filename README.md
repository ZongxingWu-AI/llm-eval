# 法律真实案例 Benchmark

本仓库实现的是一条可复现、可追溯的法律领域大模型评测流水线。业务目标不是只给模型一个总分，而是用自建、来源可追溯的真实案件题集，回答三个问题：

1. 被测模型能否准确理解法律案件材料；
2. 被测模型在不同法律能力维度上的表现是否稳定；
3. 模型或法律问答系统是否满足上线准入、人工复核和风险控制要求。

当前法律题集按九个顶层维度组织：

| dimension_id | 维度 | 典型关注点 |
|---|---|---|
| `fact_extraction` | 事实抽取 | 是否准确提取主体、时间、行为和关键事实 |
| `issue_identification` | 争议焦点识别 | 是否抓住核心争议、请求和抗辩 |
| `rule_application` | 法律规则适用 | 是否能把法律规则的构成要件对应到案件事实 |
| `evidence_evaluation` | 证据评价 | 是否理解证据、待证事实和证明力之间的关系 |
| `judgment_prediction` | 裁判结果预测 | 在不看到法院结论的前提下预测裁判方向 |
| `legal_argument` | 法律论证 | 是否形成事实—规则—结论的完整论证链 |
| `amount_calculation` | 金额计算 | 是否正确处理金额、日期、利率和计算条件 |
| `compliance_refusal` | 合规拒答 | 对不当、违法或高风险请求是否拒答并给出安全替代 |
| `procedure_time_reasoning` | 程序与时间推理 | 是否正确判断程序节点、期限和时效 |

## 四阶段总链路

```text
01 造 Benchmark
    raw → clean → extract
02 构建题集
    extract → drafts → releases → validation
03 模型作答
    release → legal_model_outputs
04 结果评测
    release + legal_model_outputs → legal_evaluation_results
```

- **01 造 Benchmark**：保留原始判决书，做无损清洗、全文信息提取和来源追踪。
- **02 构建题集**：以维度配置和题集蓝图为依据，按维度独立设计候选题、参考答案、Rubric 和来源证据，再按配额组装正式 release。
- **03 模型作答**：只调用被测模型。依据题目的 `context_type` 组织输入，保存原始回答和调用错误，不评分、不创建 JUDGE。
- **04 结果评测**：只读取正式 release 和已保存的原始回答，按 `question_id` 配对，执行 `rule`、`redline` 或 `rubric_judge` 评分，输出 PASS/REVIEW/REJECT、报告和 Excel。

## 题目输入不是只有 question

正式题目把“给模型看的材料”和“要问的问题”分开保存：

```json
{
  "dimension_id": "rule_application",
  "task_type": "法律规则适用",
  "context_type": "self_contained",
  "context": "回答所需的必要案件背景",
  "question": "具体问题",
  "reference_answer": "参考答案",
  "rubric": {},
  "source_evidence": []
}
```

`context` 是被测模型作答所需材料，`question` 只保存具体问题；`reference_answer`、`rubric` 和 `source_evidence` 不传给被测模型。案件全文仍保留在 01 的 clean/extract 数据中，题集只保存该题实际需要的必要背景或原文片段。

## 快速入口

- `methodology/01_造Benchmark/legal/ingestion/clean.py`：raw → clean 的无损解析。
- `methodology/01_造Benchmark/legal/extraction/extract.py`：从 clean 案件生成全文法律信息提取结果。
- `methodology/02_构建题集/legal/generation/generate.py`：统一维度出题引擎。
- `methodology/02_构建题集/legal/dataset/build.py`：按蓝图配额组装正式 release。
- `methodology/02_构建题集/legal/validation/validate.py`：校验维度、上下文、来源证据、泄露和可作答性。
- `methodology/03_模型作答/legal/evaluation/run.py`：生成 `legal_model_outputs.jsonl`。
- `methodology/04_结果评测/legal/scoring/run.py`：生成逐题评分、报告和 Excel。

## JSONL 转 Excel 小工具

项目根目录的 `jsonl_to_excel.py` 用于把任意“一行一个 JSON 对象”的 JSONL 文件转换成 Excel，适合人工查看数据。

先安装依赖：

```powershell
pip install -r requirements.txt
```

运行工具：

```powershell
python .\jsonl_to_excel.py
```

运行后按提示输入：

1. JSONL 输入文件的完整路径，例如 `C:\llm-eval\data\records.jsonl`；
2. Excel 输出文件的完整 `.xlsx` 路径，例如 `C:\llm-eval\data\records.xlsx`。

工具会保留字段首次出现的顺序；字典和数组会作为可读 JSON 字符串保存在单元格中，并为 Excel 添加冻结首行、筛选、自动换行和列宽。输出文件已存在时会先询问是否覆盖。

## 运行目录约定

```powershell
$repo = "C:\llm-eval"
$dataset = "$repo\methodology\01_造Benchmark\legal\data\datasets\<dataset_id>"
```

正式 release 的 SHA-256 写入 03 和 04 的运行 metadata。案件通过 `case_id` 和 `source.sha256` 追踪，题目与回答通过 `question_id` 唯一关联。更换裁判模型、评分 Prompt 或评分逻辑时，只需重跑 04，不需要再次调用被测模型。

更多字段和命令见四个 methodology 目录及批次内 `releases/README.md`。
