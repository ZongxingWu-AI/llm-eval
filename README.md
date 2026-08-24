# llm-eval：三条评测线组成的大模型评测项目

本仓库把三种常见的大模型评测能力放在一个项目中：

1. **C-Eval 客观题评测**：验证知识型选择题的准确率与基础推理能力。
2. **开放题 LLM-as-Judge**：用位置交换、多裁判投票和偏见统计比较两个模型的开放回答。
3. **法律真实案例 Benchmark**：从真实民事判决书出发，建设可追溯、可审核、可复现的垂直领域评测集。

三条线在评测对象和数据形态上相互独立，但共享模型调用、Prompt 加载、JSON 解析、数据读写和运行元数据能力。因此它们可以作为一个完整项目展示：从标准客观题，到通用开放题裁判，再到垂直领域 Benchmark 建设与评测。

## 项目结构

```text
llm-eval/
├── core/                         # 三条线共用的基础能力
│   ├── llm_client.py
│   ├── prompt_loader.py
│   ├── json_utils.py
│   ├── data_io.py
│   └── run_metadata.py
├── tracks/
│   ├── ceval/                    # 客观题评测线
│   │   ├── fetch.py
│   │   ├── evaluate.py
│   │   ├── prompts/
│   │   ├── data/
│   │   └── results/
│   ├── pairwise_judge/           # 开放题 LLM-as-Judge 评测线
│   │   ├── generate_answers.py
│   │   ├── evaluate.py
│   │   ├── pairwise.py
│   │   ├── bias_stats.py
│   │   ├── report.py
│   │   ├── prompts/
│   │   ├── data/
│   │   └── results/
│   └── legal_benchmark/          # 法律真实案例评测线
│       ├── ingestion/
│       ├── extraction/
│       ├── taxonomy/
│       ├── generation/
│       ├── dataset/
│       ├── validation/
│       ├── evaluation/
│       ├── scoring/
│       ├── prompts/
│       ├── schemas/
│       ├── data/
│       └── results/
├── tools/
│   └── export_excel.py
├── tests/
├── 学习文档/
├── README.md
├── requirements.txt
└── .env
```

根目录不再保留旧启动脚本，也不提供兼容转发入口。所有命令都使用 Python 模块方式运行。

## 环境准备

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U -r requirements.txt
Copy-Item .env.example .env
```

Linux/macOS：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U -r requirements.txt
cp .env.example .env
```

在 `.env` 中按角色配置 OpenAI 兼容接口：

- `CONTESTANT_A`、`CONTESTANT_B`：被测模型。
- `JUDGE`、`JUDGE_2`、`JUDGE_3`：开放题或法律 rubric 裁判模型。
- `GENERATOR`：法律候选题生成模型。
- `EXTRACTOR`：可选的法律结构化提取模型。
- `VALIDATOR`：可选的法律语义复核模型。

未单独设置角色时，模型地址和密钥会回退到 `DEEPSEEK_BASE_URL`、`DEEPSEEK_API_KEY`。`.env` 包含密钥，禁止提交 Git。

## 评测线一：C-Eval 客观题

适用场景：标准答案明确的知识与推理题，核心指标是准确率。

```powershell
python -m tracks.ceval.fetch --subject computer_network
python -m tracks.ceval.evaluate --subject computer_network
```

常用试跑：

```powershell
python -m tracks.ceval.fetch --subject computer_network --max-items 10
python -m tracks.ceval.evaluate --subject computer_network --max-items 10
```

数据与结果分别位于 `tracks/ceval/data/` 和 `tracks/ceval/results/`。

## 评测线二：开放题 LLM-as-Judge

适用场景：没有唯一标准答案的生成任务。项目实现了：

- 两个选手模型生成回答；
- A/B 位置交换，降低位置偏见；
- 最多三个裁判模型多数投票；
- 位置偏见、长度偏见和自我偏好相关统计；
- JSONL、Markdown、Excel 与运行元数据输出。

```powershell
python -m tracks.pairwise_judge.generate_answers
python -m tracks.pairwise_judge.evaluate
```

常用试跑：

```powershell
python -m tracks.pairwise_judge.generate_answers --max-items 3
python -m tracks.pairwise_judge.evaluate --max-items 3
```

数据与结果分别位于 `tracks/pairwise_judge/data/` 和 `tracks/pairwise_judge/results/`。

## 评测线三：法律真实案例 Benchmark

### 第一版范围

- 民事一审判决书；
- 合同、准合同纠纷；
- 劳动争议；
- 侵权责任纠纷；
- 婚姻家庭、继承纠纷；
- 物权纠纷；
- 每类约 10 份，首批约 50 份案例。

这是独立的垂直领域 Benchmark，不与 Pairwise Judge 共享内部业务代码。两者只共同使用 `core/` 的通用能力。

### 数据生命周期

```text
raw 原始判决书
    ↓
无损分段解析
    ↓
结构化法律信息提取
    ↓
规则一致性校验
    ↓
人工审核
    ↓
候选问题与 Rubric 生成
    ↓
人工审稿
    ↓
正式题集
    ↓
模型回答与评分
    ↓
失败分析和评测报告
```

#### 1. 放入原始案例

一份判决书一个 `.md` 或 `.txt` 文件，放在：

```text
tracks/legal_benchmark/data/raw/
```

该目录中的真实文书已被 `.gitignore` 忽略，只在本地保存。不要提交未经来源、隐私和质量审核的原文。

#### 2. 无损解析

```powershell
python -m tracks.legal_benchmark.ingestion.clean
```

解析器保留 `full_text`，提取案号、法院、日期、审级、多方当事人、诉讼请求、答辩、事实、证据、法院说理、判决主文、法条、金额、日期和利息表达，并记录 SHA-256、解析器版本和质量状态。`facts_summary` 只是派生字段，不替代全文。

#### 3. 结构化提取

默认使用可重复的规则提取：

```powershell
python -m tracks.legal_benchmark.extraction.extract
```

需要模型辅助时：

```powershell
python -m tracks.legal_benchmark.extraction.extract --use-llm
```

模型结论必须同时保存 `source_section` 和 `source_quote`，且引用必须能在相应章节中定位，否则不会被接受。

#### 4. 生成候选题

```powershell
python -m tracks.legal_benchmark.generation.generate --questions-per-case 2
```

候选题进入 `data/drafts/`，初始状态是 `review_status: pending`，必须人工核对题目、参考答案、Rubric、分类标签和证据来源。

#### 5. 组装正式题集

人工审核通过后，把候选题状态改为 `review_status: approved`，再运行：

```powershell
python -m tracks.legal_benchmark.dataset.build
```

开发试跑可以显式包含待审题，但不能用于正式发布：

```powershell
python -m tracks.legal_benchmark.dataset.build --include-pending --max-items 5
```

#### 6. 校验

```powershell
python -m tracks.legal_benchmark.validation.validate
```

可选模型语义复核：

```powershell
python -m tracks.legal_benchmark.validation.validate --llm-check
```

校验内容包括必填字段、受控 taxonomy、来源定位、重复题和同案 split 隔离。

#### 7. 运行法律评测

```powershell
python -m tracks.legal_benchmark.evaluation.run
```

支持三种评分方式：

- `rule`：必答点、加分点和扣分项的确定性检查；
- `redline`：高风险任务的拒答与安全引导检查；
- `rubric_judge`：裁判模型根据参考答案和 Rubric 评分。

结果只写入 `tracks/legal_benchmark/results/`，不会污染另外两条评测线。

### 法律分类体系

案件级和问题级分类分开保存。

案件级核心字段：

```json
{
  "domain": "民事",
  "procedure_stage": "一审",
  "document_type": "判决书",
  "primary_category": "合同、准合同纠纷",
  "cause_path": ["合同、准合同纠纷", "买卖合同纠纷"],
  "procedure_tags": [],
  "evidence_tags": []
}
```

问题级核心字段：

```json
{
  "primary_issue": "逾期付款利息起算时间",
  "task_type": "争议焦点识别与规则适用",
  "reasoning_capabilities": ["事实抽取", "法律规则适用", "证据评价"],
  "answer_type": "结构化论述",
  "scoring_method": "rubric_judge",
  "difficulty": "medium",
  "source_evidence": []
}
```

受控词表位于 `tracks/legal_benchmark/taxonomy/taxonomy.json`，题目 schema 位于 `tracks/legal_benchmark/schemas/`。

### 为什么没有 train 集

当前目标是评测模型，不是训练法律模型，因此不建立传统训练集。首批约 50 个案例按 `case_id` 固定划分：

- `dev`：15 案，用于调试解析器、Prompt、Rubric 和评分逻辑；
- `calibration`：10 案，用于比较人工评分、规则评分和 LLM Judge 的一致性；
- `test`：25 案，冻结配置后用于最终模型比较和项目报告。

每个一级方向计划分为 3 个 dev、2 个 calibration、5 个 test。同一案例生成的所有问题必须进入同一个 split，禁止同案问题跨集合。

### 发布与隐私原则

正式 release 只应包含：

- 经审核且允许公开的结构化字段；
- 脱敏后的题目与参考答案；
- 评分标准；
- 来源哈希和处理版本；
- 必要的短引用或证据定位。

原始判决书、中间解析文件、候选草稿和运行结果默认不提交 Git。taxonomy、schema、发布 manifest 和经审核的 release 可以纳入版本控制。

## 通用 Excel 导出

指定输入和输出：

```powershell
python -m tools.export_excel --input tracks/legal_benchmark/data/releases/legal_questions.jsonl --output legal_questions.xlsx
```

不指定输入时，会扫描三条评测线的数据与结果目录：

```powershell
python -m tools.export_excel
```

## 测试

```powershell
python -m unittest discover -s tests -v
```

所有命令均支持 `--help`；主要运行命令支持 `--input`、`--output` 和 `--max-items` 或等价试跑参数。

## 简历表述示例

> 独立搭建模块化大模型评测平台，覆盖 C-Eval 客观题准确率评测、开放题 LLM-as-Judge 成对比较，以及真实民事判决书法律 Benchmark 建设；实现统一多模型调用、Prompt 与结构化输出解析、位置交换和多裁判投票、偏见统计、无损法律文书解析、多标签 taxonomy、证据可追溯出题、案件级数据划分、规则与 Rubric 混合评分、自动校验和报告生成。

这三条线的递进关系是：**标准 Benchmark 使用能力 → 开放题裁判系统能力 → 垂直领域 Benchmark 从数据到评测的完整建设能力**。
