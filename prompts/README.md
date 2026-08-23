# 提示词模板

这里存放评测提示词，代码只负责加载和替换占位符，内容可以随时改。

- `ceval_prompt.md`：客观题（C-Eval）提示词，占位符 `{{question}} {{A}} {{B}} {{C}} {{D}}`。
- `judge_prompt.md`：裁判提示词主框架，占位符 `{{question}} {{answer_a}} {{answer_b}} {{rubric}}`。
- `judge_rubric.md`：裁判评分标准（5 维打分 + 长度中性 + 输出 JSON 格式）。

改提示词直接编辑对应 md 文件即可，不用动 Python 代码。
