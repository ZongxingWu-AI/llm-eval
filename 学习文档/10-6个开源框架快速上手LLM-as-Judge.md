# 6个开源框架，快速上手LLM-as-Judge

---

## 💡 一句话理解 Model-as-Judge

大模型输出是非确定的——同一个 prompt 改一个词，可能在某个你从没测过的场景里突然"翻车"。

人工审不过来，正则匹配又抓不住语义。**Model-as-Judge 就是让另一个 LLM 来当裁判**，给输出打分、做对比、找问题。

这个方法现在已经是 prompt 迭代、RAG 评估、模型 A/B 测试的标配。

## 📊 为什么只聊这 6 款？

GitHub 上相关项目 30+，筛选标准就三条：

| 筛选维度 | 具体标准 |
|----------|----------|
| 🔧 维护活跃度 | 近 6 个月有持续代码提交，非"发完论文就躺平" |
| 👥 社区规模 | GitHub Stars 数量 + issue 响应速度 |
| 🚀 工程可用性 | 有文档、有安装包、能接 CI/CD，不是纯研究代码 |

> ⚠️ **已被排除**：PandaLM、Auto-J 等（维护停滞或工程化不足）

## 📈 6 款工具速览表

| 工具 | ⭐ Stars | 维护方 | 维护状态 | 活跃度 |
|------|----------|--------|----------|--------|
| **promptfoo** | 11k+ | OpenAI（2025.9 收购） | 持续更新 | 🔥 极活跃 |
| **OpenCompass** | 3.0k+ | 上海 AI Lab | 活跃维护 | ✅ 活跃 |
| **DeepEval** | 5.0k+ | Confident AI | 持续迭代 | ✅ 活跃 |
| **lm-evaluation-harness** | 10k+ | EleutherAI | 维护中 | ⚠️ 一般 |
| **RAGAS** | 8.0k+ | ExplodingGradients | 版本迭代快 | ✅ 活跃 |
| **Giskard** | 4.9k+ | Giskard AI（法国） | 活跃维护 | ✅ 活跃 |

## 🔍 逐款详解

### ❶ promptfoo — 红队 + CI/CD 首选

> **GitHub**: promptfoo/promptfoo ｜ **License**: 开源 ｜ **2025.9 被 OpenAI 收购**

**核心能力**

- ✅ YAML 声明式配置，不写代码就能定义测试集
- ✅ 多模型并行 A/B 对比（GPT / Claude / Gemini / Llama / 本地模型）
- ✅ 红队测试：自动生成越狱、注入、PII 泄露攻击，覆盖 OWASP / NIST / MITRE ATLAS / EU AI Act
- ✅ 10+ 断言类型：精确匹配 / 正则 / LLM-rubric / 自定义脚本 / 延迟 / 成本
- ✅ 本地 Web 看板：`promptfoo view` 一键启动

**客观评价**

| 维度 | 说明 |
|------|------|
| ✅ 上手成本 | 低，`npx promptfoo@latest init` 数分钟完成初始化 |
| ⚠️ 技术栈 | Node.js 生态，前端/Node 开发者友好，纯 Python 团队需适应 |
| ⚠️ 中文支持 | 红队攻击策略偏英文，中文定制需自行开发 plugin |
| 💡 定位 | 更偏向"测试执行引擎"，LLM-rubric 断言可实现 Judge 功能 |

**适合**：应用开发者、安全工程师、CI/CD 集成需求、红队评测

### ❷ OpenCompass（司南评测）— 学术综合评测

> **GitHub**: open-compass/opencompass ｜ **License**: 开源 ｜ **上海 AI Lab 维护**

**核心能力**

- ✅ 100+ 数据集、52+ 学科（C-Eval、MMLU、GSM8K、HumanEval 等）
- ✅ 多种 Judge 模式：单点评分 / 对照评分 / Rubric 评分
- ✅ 支持自定义数据集与裁判 prompt
- ✅ 在线竞技场：opencompass.org.cn/arena
- ✅ 分布式评测，支持千亿参数模型

**客观评价**

| 维度 | 说明 |
|------|------|
| ✅ 学术认可度 | 高，发论文时评测数据易被认可 |
| ✅ 中文支持 | C-Eval / CMMLU 等国内榜单开箱即用 |
| ⚠️ 环境配置 | 依赖 Docker，镜像约 8GB，首次配置耗时较长 |
| ⚠️ 学习成本 | 配置文件为 Python 格式（非 YAML），中等 |
| ⚠️ 文档 | 自定义 Judge prompt 示例较少，需翻 issue 区 |

**适合**：科研团队、企业级评测平台、论文项目

### ❸ DeepEval — Python 工程团队

> **GitHub**: confident-ai/deepeval ｜ **License**: 开源 ｜ **Confident AI 运营**

**核心能力**

- ✅ G-Eval：GPT-4 chain-of-thought 打分机制
- ✅ 20+ 指标：Answer Relevancy、Faithfulness、Bias、幻觉检测
- ✅ 原生 pytest 集成，直接嵌入 CI/CD
- ✅ 支持本地模型（Ollama）与闭源 API 混用
- ✅ 内置红队测试集

**客观评价**

| 维度 | 说明 |
|------|------|
| ✅ 上手成本 | 低，pip install 即可，约 20 分钟跑通首个测试 |
| ✅ Python 友好 | API 与 pytest 一致，开发者零学习成本 |
| ⚠️ API 依赖 | 部分指标依赖 OpenAI API，成本敏感场景需注意 |
| ⚠️ 学术积累 | 2023 年开源，论文引用少于 OpenCompass / lm-evaluation-harness |
| 💡 商业化 | Confident AI 提供付费 SaaS，核心框架保持开源 |

**适合**：Python 技术栈团队、RAG 项目、CI/CD 集成

### ❹ lm-evaluation-harness — 学术基准"事实标准"

> **GitHub**: EleutherAI/lm-evaluation-harness ｜ **License**: 开源 ｜ **HuggingFace Leaderboard 底层引擎**

**核心能力**

- ✅ 500+ 评测任务（MMLU、HellaSwag、GSM8K、TruthfulQA、HumanEval 等）
- ✅ 支持 100+ 模型（HuggingFace、OpenAI、Anthropic、本地部署）
- ✅ 极简 CLI：`lm_eval --model hf --tasks mmlu --model_args pretrained=xxx`

**客观评价**

| 维度 | 说明 |
|------|------|
| ✅ 学术地位 | 论文 benchmark 的事实标准，引用量最高 |
| ✅ 覆盖广度 | 500+ 任务，无同类工具可替代 |
| ⚠️ Judge 能力 | 设计初衷是跑标准 benchmark，自定义裁判需改源码 |
| ⚠️ 工程化 | 环境配置复杂，依赖冲突常见，上手门槛高 |
| ⚠️ 文档风格 | 偏学术，工程开发者友好度一般 |

**适合**：研究人员、论文项目、标准 benchmark 需求

### ❺ RAGAS — RAG 专项"指标全家桶"

> **GitHub**: explodinggradients/ragas ｜ **License**: 开源 ｜ **8k+ stars**

**核心能力**

- ✅ 核心指标：Faithfulness、Answer Relevancy、Context Precision、Context Recall
- ✅ 支持自定义指标扩展
- ✅ 测试集自动生成：从文档自动产出 QA 对
- ✅ 与 LangChain / LlamaIndex 生态集成

**客观评价**

| 维度 | 说明 |
|------|------|
| ✅ RAG 指标 | 定义清晰，学术验证充分，场景专用 |
| ✅ 自动生成 | 测试集生成可节省人工标注时间 |
| ✅ 社区活跃 | 8k+ stars，版本迭代快 |
| ⚠️ 场景局限 | 仅限 RAG，通用对话 / 代码生成无法直接复用 |
| ⚠️ API 依赖 | 部分指标依赖 GPT-4，API 变动较频繁 |

**适合**：RAG 应用开发、检索质量评估

### ❻ Giskard — QA + 安全一体化

> **GitHub**: Giskard-AI/giskard ｜ **License**: 开源 ｜ **法国初创**

**核心能力**

- ✅ 内置指标：正确性、相关性、事实性、偏见检测
- ✅ 自动生成测试用例：基于模型输出发现薄弱环节
- ✅ 安全测试：注入、越狱、PII 泄露检测
- ✅ 桌面应用：`giskard scan` + 可视化看板

**客观评价**

| 维度 | 说明 |
|------|------|
| ✅ 双模式 | 桌面应用 + SDK，非技术人员可参与 |
| ✅ 自动生成 | 测试用例自动生成，减少人工标注 |
| ✅ 一体化 | 安全测试 + 质量评估同一平台 |
| ⚠️ 中文支持 | 社区以英文为主，中文场景需自行定制 |
| ⚠️ 付费功能 | 部分高级功能需 Cloud 版 |
| ⚠️ 学术引用 | 较少 |

**适合**：QA + 安全一体化测试、非技术人员参与评测

## 🌐 扩展生态：其他值得关注

| 工具 | 定位 | 补充场景 |
|------|------|----------|
| **TruLens** | 评估 + 链路追踪 | 调试 LLM 行为、查看 token 消耗和中间步骤 |
| **Phoenix (Arize)** | 生产可观测性 | 已有传统 ML 监控，需平滑扩展到 LLM |
| **MLflow** | AI 工程平台 | 端到端 MLOps（评估 + 追踪 + 实验管理） |
| **Evidently** | 数据科学评估 | 快速生成评估报告、合成测试数据 |
| **OpenAI Evals** | 模型级基准测试 | 研究场景、高度定制化评估逻辑 |

## 🗺️ 选型决策树（三步走）

> 文章仅展示 **Step 1** 的开头：「你评测什么？」，后续决策树内容未在抓取文本中完整呈现，如需完整决策树可访问原文查看。

## 🛠️ CI/CD 实战：promptfoo 配置

### ① 初始化项目

```
npx promptfoo@latest init
```

生成目录结构：

```
my-llm-project/
```

### ② 配置文件 `promptfooconfig.yaml`

```
prompts:
```

> 说明：原文中该代码块仅展示了 `prompts:` 一行，后续 YAML 配置内容未在抓取文本中完整呈现。

> 💡 `llm-rubric` 即 Model-as-Judge 的核心用法：由 LLM 按标准给回答打分。

### ③ 本地运行

```
# 执行评测
```

### ④ GitHub Actions 配置（`.github/workflows/llm-eval.yml`）

```
name: LLM Evaluation
```

> ⚠️ **安全提醒**：在 GitHub 仓库 `Settings → Secrets → Actions` 中配置 `OPENAI_API_KEY`，**切勿将密钥写入 YAML 文件**。

> 🐍 **Python 团队替代**：用 `pip install deepeval` + pytest 集成，Actions 逻辑相同。

## ⚠️ Model-as-Judge 使用 checklist

实施前建议逐条核对：

| # | 注意事项 | 说明 |
|---|----------|------|
| 1 | 📋 建立人类黄金标准 | 无人工标注基准，无法验证裁判一致性 |
| 2 | 🔄 避免同族偏见 | GPT-4 评 GPT-4 易偏高，建议跨模型评判 |
| 3 | 📝 评分标准具体化 | 避免"打分 1-10"，用结构化 rubric |
| 4 | 🕐 定期校准 | 裁判偏好 60-90 天可能漂移，需周期性人工验证 |
| 5 | 🔌 评估与生产解耦 | 评估逻辑独立于用户请求链路，避免增加延迟 |
| 6 | 🗳️ 高 stakes 多裁判 | 关键场景用多个裁判模型取平均或投票 |
| 7 | 📏 控制长度偏见 | verbose 回答易获高分，标准中需明确限制 |
| 8 | 🎲 消除顺序偏见 | 成对对比时随机化答案顺序 |
| 9 | 💰 追踪评估成本 | API + token 消耗可能接近生产环境 |
| 10 | 🏷️ 评分标准版本化 | prompt 变更纳入版本管理，便于追溯 |

## 🎯 一句话总结

| 工具 | 一句话定位 |
|------|------------|
| **promptfoo** | 跨语言 CI/CD + 红队测试，OpenAI 收购背书 |
| **OpenCompass** | 学术首选，中文数据集完善，分布式评测 |
| **DeepEval** | Python 原生 pytest 集成，工程化 CI/CD |
| **lm-evaluation-harness** | 500+ 任务，论文 benchmark 事实标准 |
| **RAGAS** | RAG 专项指标最全，测试集自动生成 |
| **Giskard** | 桌面应用 + 安全 QA 一体化，非技术友好 |

> **没有单一工具能覆盖所有场景。** 生产环境通常需要组合：一个轻量框架做 CI 卡点，一个平台做持续监控和人工复核。

---

*原文链接：https://mp.weixin.qq.com/s/dp9KREINjJxmgv3UgCRPEw*
