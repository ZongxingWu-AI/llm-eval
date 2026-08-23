# llm-eval：大模型评测学习项目

从零搭起来的评测流水线，目前有三条评测线：

| 评测线 | 做什么 | 对应文档 |
|---|---|---|
| A. 客观题 | 用 C-Eval 选择题跑模型正确率 | 07/08 |
| B. 开放题裁判 | LLM-as-Judge 成对比较 + 三大偏见 | 09/10/14 |
| C. 自建法律题集 | 真实判决书 → 清洗 → 出题 → 校验 → 判分 | 12/13 |

## 目录结构

```text
llm-eval/
├── runner/llm_client.py    # 统一调模型（多 provider、重试、温度、思考兜底）
├── prompts/                # 提示词模板（md，改提示词不动代码）
│   ├── loader.py
│   └── templates/*.md
├── judge/pairwise.py       # 成对比较核心（纯逻辑）
├── metrics/bias_stats.py   # 裁判三大偏见统计
├── metrics/legal_scorer.py # 法律题集判分（规则/红线/裁判）
├── report/writer.py        # 裁判报告落盘
├── data/
│   ├── raw/                # ① 放真实判决书（txt/md）
│   ├── cleaned/            # ② 清洗后的案情
│   ├── drafts/             # ③ 草稿（人工 / AI 出题）
│   ├── legal_dimensions.json
│   └── legal_questions.jsonl  # ④ 正式题集
├── results/<时间戳>/       # 每次运行的结果目录（历史保留）
├── fetch_ceval.py / run_ceval.py
├── generate_answers.py / judge.py
├── clean_judgments.py / generate_drafts.py
├── build_legal_dataset.py / validate_dataset.py / run_legal_eval.py
└── to_excel.py
```

## 环境准备（一次性）

```bash
cd llm-eval
python3 -m venv .venv
source .venv/bin/activate
pip install -U -r requirements.txt
cp .env.example .env   # 填入 DEEPSEEK_API_KEY，需要时可填其他模型
```

## 换模型

在 `.env` 里按角色前缀填 `BASE_URL` / `API_KEY` / `MODEL`：

- `CONTESTANT_A` / `CONTESTANT_B`：被测选手
- `JUDGE` / `JUDGE_2` / `JUDGE_3`：裁判（可多裁判投票）
- 未填时自动回退到 DeepSeek；换千问 / MiniMax 时三个都要填，尤其 `API_KEY` 不能留空

## 流程 A：客观题 C-Eval

```bash
python fetch_ceval.py --subject computer_network   # 下载题集
python run_ceval.py --subject computer_network     # 跑分
```

结果在 `results/ceval_computer_network.jsonl`（根目录，旧格式）。

## 流程 B：LLM-as-Judge 成对比较

```bash
python generate_answers.py          # 两个选手各生成 5 题回答
python judge.py                     # 裁判成对比较 + 位置交换 + 三大偏见统计
```

结果在 `results/<时间戳>/`：`judge_pairs.jsonl` / `judge_pairs.xlsx` / `judge_report.md`。

## 流程 C：法律自建题集（重点）

```bash
# 1) 把真实判决书（txt/md）放进 data/raw/，一个文件一份判决书

# 2) 清洗（纯代码规则，不调模型；可重复跑，自动跳过已处理）
python clean_judgments.py

# 3) 出题，两种方式：
#    3a. 人工：直接在 data/drafts/legal_drafts.jsonl 里按真实案情写题，一行一题
#    3b. AI 辅助：批量生成候选草稿
python generate_drafts.py --max-cases 5

# 4) 人工审稿（关键一步）：打开 data/drafts/legal_drafts.jsonl，
#    逐条修改/删除；通过的把 "待审": true 改成 "待审": false
#   （带待审标记的不会进正式题集）

# 5) 组装题集
python build_legal_dataset.py

# 6) 校验（纯规则，不花钱）
python validate_dataset.py

# 7) 评测判分
python run_legal_eval.py
```

常用参数：

- `--max-questions N`：三条评测线都支持，只跑前 N 题
- `generate_drafts.py --cases "case_0001,case_0002" --questions-per-case 3`：指定案情、每案题数
- `validate_dataset.py --llm-check`：加模型语义复核（默认关，省 token）

## 通用工具

```bash
python to_excel.py   # 把 data/ 和 results/ 下的 jsonl 全部转成同名 xlsx
```

## 数据字段速查

- 草稿 / 题集字段：`based_on_case`、`维度`、`类型`（正向|负向）、`问题`、`标准答案要点`、`评分细则{必答点,加分项,扣分项}`、`参考法条`、`安全敏感`、`判分方式`
- 判分方式：`规则`=关键词/数字比对；`红线`=负向题拒绝判定；`裁判`=调模型按 rubric 打分

## 常见问题

- 运行时打印「已从 NO_PROXY 移除 IPv6 条目」：正常，脚本自动兼容本机代理。
- 全部显示「无答案」：思考类模型 `max_tokens` 默认 8192，不要改小；非思考模型可调小 `DEEPSEEK_MAX_TOKENS`。
- `.env` 不要提交 git；`.env.example` 只放占位符。
- hf-mirror 不支持 datasets 的 API 路径，默认走 `huggingface.co`（本机代理可达）。
