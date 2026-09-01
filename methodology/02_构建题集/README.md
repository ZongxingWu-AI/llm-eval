# 02 构建题集：维度驱动的法律题集设计

02 的业务职责是把 01 产出的案件材料转化为**可独立作答、可追溯评分、可按能力分析**的候选题和正式 release。

## 核心设计

本项目不为每个维度复制一套 Python 流程，而采用：

```text
统一出题引擎 + 九类维度配置 + 每维一个 Prompt 模板 + 统一校验与组装
```

九个顶层维度为：事实抽取、争议焦点识别、法律规则适用、证据评价、裁判结果预测、法律论证、金额计算、合规拒答、程序与时间推理。`dimension_id` 是机器统计和筛选的稳定键，`task_type` 是面向业务人员的任务名称。

维度配置位于 `methodology/02_构建题集/legal/config/dimension_catalog.json`，其中定义适用案件类型、目标题量、上下文策略、推荐评分方式、必答点、难度和风险分布；独立配额蓝图位于 `methodology/02_构建题集/legal/config/dataset_blueprint.json`。题集蓝图根据这些目标按维度配额跨案件组装 release；一个案件不要求覆盖全部维度。

## 题目契约

正式题目至少包含：

```json
{
  "question_id": "legal_case_001_01",
  "dimension_id": "rule_application",
  "task_type": "法律规则适用",
  "context_type": "self_contained",
  "context": "回答所需的必要案件背景",
  "question": "具体问题",
  "reference_answer": "参考答案",
  "rubric": {},
  "source_evidence": [{"source_quote": "原文连续片段", "source_quote_sha256": "本地生成的哈希"}]
}
```

`context` 保存被测模型真正需要看到的材料，`question` 只描述要回答的具体问题。不能把回答所依赖的材料藏在“上文”或未传入的案件里；也不能把 `reference_answer`、法院结论或评分提示泄露给被测模型。案件全文仍保留在 01 的 clean/extract 数据中。

## 工作步骤

1. 读取 extract 案件的全文、分块结果和法律事实地图。
2. 依据维度配置选择 Prompt，不按案件固定生成同一种题。
3. 针对目标维度生成候选题、必要 `context`、参考答案、Rubric 和 `source_evidence`。
4. 做结构、taxonomy、维度映射、材料可定位、答案不泄露和可作答性校验。
5. 人工审核候选题，确认事实、法条版本、答案要点和风险标签。
6. 使用题集蓝图按维度配额组装 release，并输出维度、案件类别、难度和风险覆盖统计。
7. 对冻结 release 做最终 validation，全部关键失败修复后才能进入 03。

## 主要入口

- `legal/generation/generate.py`：统一维度出题引擎；统一处理读取材料、Prompt 路由、重试、解析和错误记录。支持按“案件 × 维度 × 题型请求”并发调用出题模型。`workers` 控制最大并发工作线程数，`qps` 控制整个进程的请求启动速率；两者只影响执行速度，不改变题目契约、事实地图门禁、校验和正式题集组装规则。
- `legal/config/dimension_catalog.json`：九类维度、上下文策略和评分口径。
- `legal/config/dataset_blueprint.json`：正式题集按维度、案件类别、难度和风险的目标配额。
- `legal/dataset/build.py`：按维度配额组装 release，保留案件级 split。
- `legal/dataset/split.py`：确保同一个 `case_id` 不跨 split。
- `legal/validation/validate.py`：验证题面能否在只提供 `context + question` 时作答，并校验来源证据和答案泄露。

02 的输出是候选题草稿、拒绝/错误记录、正式 release、manifest、validation 结果和覆盖统计；不调用被测模型，也不产生模型评测分数。

## 并发生成候选题

蓝图模式会把每个案件与每个“维度 × 题型”请求拆成独立任务，再使用共享的进程级限流器调用出题模型。输出和错误文件仍按输入案件、蓝图请求和模型返回顺序稳定写出；单个请求失败不会中断其他请求。

```powershell
Set-Location 'C:\llm-eval'

$py = 'C:\Users\Modelbest-Intel\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'

& $py -m methodology.02_构建题集.legal.generation.generate `
  --input 'C:\llm-eval\methodology\01_造Benchmark\legal\data\datasets\legal_20260827_001\extract\legal_cases_extract.jsonl' `
  --output 'C:\llm-eval\methodology\02_构建题集\legal\data\legal_question_candidates_smoke.jsonl' `
  --blueprint 'C:\llm-eval\methodology\02_构建题集\legal\config\dataset_blueprint_smoke.json' `
  --max-items 10 `
  --workers 10 `
  --qps 10
```

其中 `--max-items 10` 表示只处理前 10 个案件；`--workers 10` 表示最多同时执行 10 个请求；`--qps 10` 表示整个进程每秒最多启动约 10 个模型请求。如果服务商限流较低，可以保留 10 个工作线程并降低启动速率，例如 `--workers 10 --qps 3`。未指定蓝图时，旧的 `--questions-per-case` 模式仍保持每案一次任务的兼容行为，并同样使用共享限流器。
