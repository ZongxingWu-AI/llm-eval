#!/usr/bin/env python3
"""裁判提示词：从 md 模板加载并渲染，内容与代码解耦。"""

from prompts import loader  # 加载与渲染提示词模板


def build_judge_prompt(question, answer_a, answer_b):
    """加载裁判提示词和评分标准两个 md，填入题目与两版回答。

    输入：
      question 题目文本；
      answer_a 选手 A 的回答文本；
      answer_b 选手 B 的回答文本。
    输出：一个多行字符串提示词。

    为什么拆两个 md：主框架（judge_prompt.md）和评分标准（judge_rubric.md）
    分开编辑——改题目排版不改评分标准，改评分标准不改框架。
    """
    # 运行前：question / answer_a / answer_b 是三个字符串。
    # 运行后：prompt_template 变成主框架文本，rubric 变成评分标准文本。
    prompt_template = loader.load_template("judge_prompt.md")
    rubric = loader.load_template("judge_rubric.md")
    # 运行后：prompt 变成占位符被替换掉的完整提示词，例如
    #   "你是一个客观公正的评测裁判。……\n问题：……\n回答A：……\n回答B：……\n评分维度……"
    prompt = loader.render(
        prompt_template,
        {
            "question": question,
            "answer_a": answer_a,
            "answer_b": answer_b,
            "rubric": rubric,
        },
    )
    return prompt
