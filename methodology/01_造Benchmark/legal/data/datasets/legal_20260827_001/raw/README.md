# raw：原始案件

## 目录职责

`raw/` 是一个数据批次的原始输入层。一案一文件，保留从来源取得的案件文本；本阶段不做摘要、不调用大模型、不把解析后的字段写回原文件。

## 文件

- `*.md`：单份原始案件全文。文件名便于人工识别，但稳定追踪应以 clean 记录中的 `case_id` 和 `source.sha256` 为准。
- `README.md`：本阶段说明。

## 与下游的关系

`clean.py` 读取这里的案件，生成 `<dataset>/clean/legal_cases_clean.jsonl` 和 `<dataset>/manifests/legal_sources.jsonl`。如果原始文件内容发生变化，SHA-256 应随之变化，旧的下游结果不应被默认为仍然有效。

具体批次路径通过命令行指定，旧的历史 `data/raw/` 不属于新批次的默认入口。
