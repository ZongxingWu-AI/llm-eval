# 法律 Benchmark 教学总索引

当前仓库只保留法律真实案例 Benchmark。四个目录对应教学文档中的四个环节：

```text
造 Benchmark → 构建题集 → 当裁判 → 跑项目
```

C-Eval 与 LLM-as-Judge 已迁移到 ``C:\\CEval-LLMJudge``，本索引不再登记它们的业务代码。
法律线的数据流是：

```text
raw 判决书 → parsed → cleaned → drafts → releases → 模型回答 → 评分结果
```

## 四个目录

- ``01_造Benchmark``：解析原始判决书、保留全文、提取章节和法律信息。
- ``02_构建题集``：生成候选题、人工审核、组装 release、案件级划分和校验。
- ``03_当裁判``：选择规则/Rubric 评分方法，输出 PASS/REVIEW/REJECT。
- ``04_跑项目``：批量运行法律题集，保存结果、报告和运行元数据。

公共基础层位于 ``core``，由四个法律环节共同调用，不属于某一个环节。
