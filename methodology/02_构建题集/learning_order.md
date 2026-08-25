# 02 构建题集学习顺序：法律 Benchmark

1. 阅读生成 Prompt，理解问题、参考答案、Rubric 和 source_evidence。
2. 用 1 案生成少量候选题，不要立即跑 50 案。
3. 人工检查事实依据、分类、难度、风险和引用，把合格题改为 ``approved``。
4. 运行 ``build.py``，观察题号、版本、拒绝原因和案件级 split。
5. 运行 ``validate.py``，修复所有 fail 后才进入评分环节。
