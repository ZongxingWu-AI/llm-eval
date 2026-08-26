# llm-eval：法律 Benchmark 项目

本仓库当前承载：基于真实民事一审判决书构建法律领域大模型评测集。

## 项目结构

```text
C:\\llm-eval\\
├── core\\                         # 法律项目公共基础层
├── methodology\\
│   ├── 01_造Benchmark\\legal\\   # 原始判决书解析和法律信息提取
│   ├── 02_构建题集\\legal\\       # 候选题、审核、正式题集和 split
│   ├── 03_当裁判\\legal\\         # 法律规则、红线和 Rubric 评分
│   └── 04_跑项目\\legal\\         # 批量评测、报告和结果导出
├── tests\\                         # 法律线测试
├── 学习文档\\
└── .env
```

## 四个环节

1. **造 Benchmark**：raw 判决书 → parsed 案件 → cleaned 法律信息。
2. **构建题集**：结构化案件 → 候选题 → 人工审核 → release → 案件级 split。
3. **当裁判**：被测回答与参考答案、Rubric 和来源证据对照，输出 PASS/REVIEW/REJECT。
4. **跑项目**：批量调用被测模型和评分器，生成逐题结果、错误、报告和运行元数据。

法律线的手动入口依次是：

```powershell
Set-Location C:\\llm-eval
python -m methodology.01_造Benchmark.legal.ingestion.clean --help
python -m methodology.01_造Benchmark.legal.extraction.extract --help
python -m methodology.02_构建题集.legal.generation.generate --help
python -m methodology.02_构建题集.legal.dataset.build --help
python -m methodology.02_构建题集.legal.validation.validate --help
python -m methodology.04_跑项目.legal.evaluation.run --help
```

## 法律数据生命周期

```text
data/raw 或 data/raw_selected_50
    ↓ clean.py
parsed
    ↓ extract.py
cleaned
    ↓ generate.py + 人工审核
 drafts
    ↓ build.py
releases
    ↓ validate.py
法律评测结果目录
```

raw 判决书、中间 JSONL、候选题、运行结果和本地 manifest 只在本地使用，均由
``.gitignore`` 忽略；README、Prompt、Schema、Taxonomy 和代码可以提交。
不要把 API 密钥写入仓库，也不要执行跨项目复制原始法律数据。

详细学习地图见 ``methodology/README.md`` 和四个教学目录中的 ``README.md``、
``module_map.md``、``learning_order.md``。
