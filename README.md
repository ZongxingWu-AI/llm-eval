# llm-eval：DeepSeek 跑 C-Eval 单学科评测（第一阶段）

对应文档 07/08：跑一遍真实公开评测集，掌握「取题 → 拼 prompt → 调 API → 提取答案 → 对比判分 → 分析」的完整闭环。

## 环境准备（一次性）

```bash
cd llm-eval
python3 -m venv .venv
source .venv/bin/activate
pip install -U -r requirements.txt
```

## 配置 API key

```bash
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY=sk-...
```

## 使用

```bash
# 1) 下载 C-Eval 单个学科（默认 computer_network，约 19 题）
python fetch_ceval.py --subject computer_network

# 2) 真实跑分
python run_ceval.py --subject computer_network
# 常用参数：--max-questions 5 只跑前 5 题；--subject 可换学科
```

输出：

- `data/ceval_computer_network.jsonl`：题集
- `results/ceval_computer_network.jsonl`：每题结果（含 model_answer / is_correct / error）

## 设计要点（对应文档）

- temperature=0 + 固定 prompt，保证可复现（07）
- 3 次重试 + 题间 0.5s 控速，避免限流（08）
- 只输出字母的 prompt 模板，答案提取兼容「答案是 B」等写法（07）

## 常见问题

- 运行时打印「已从 NO_PROXY 移除 IPv6 条目」：这是脚本自动兼容本机代理环境（`::1` 会让 datasets 报 `Invalid port: ':1'`），正常现象，无需处理。
- 如果网络无法直连 `huggingface.co`：可显式设置 `export HF_ENDPOINT=https://hf-mirror.com` 后重跑（注意该镜像不支持 datasets 的 API 路径，若仍失败请反馈）。
- 全部显示「无答案」：思考类模型（如 `deepseek-v4-flash`）会先输出大段思考过程再给答案，`max_tokens` 太小会被思考耗尽。脚本默认 `max_tokens=8192`（可用 `DEEPSEEK_MAX_TOKENS` 覆盖）；若改用非思考模型（如 `deepseek-chat`）会更省更快。

## 下一步

- 跑全部 52 学科 + 分学科 / Bad Case 分析
- LLM-as-Judge 开放题评测（09/10/14）
- 医疗药品自建数据集（12/13）
