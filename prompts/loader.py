#!/usr/bin/env python3
"""加载 prompts/templates 下的提示词模板，并用占位符渲染。

模板里用 {{key}} 表示占位符，例如 {{question}}、{{answer_a}}、{{rubric}}。
调用 render 时，把 key 对应的值填进去，返回最终提示词。
这样提示词内容在 md 文件里，和代码解耦，改提示词不用改代码。
"""

import os  # 用来拼路径、判断文件是否存在


# 模板目录：本文件在 llm-eval/prompts/ 下，模板放在它下面的 templates/。
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


def load_template(name):
    """读取模板文件内容。

    输入：模板文件名，例如 "ceval_prompt.md"。
    输出：模板文本（字符串，里面可能还留着 {{...}} 占位符）。
    """
    # 运行前：name 是文件名，例如 "judge_prompt.md"。
    # 运行后：path 变成模板文件的完整路径。
    path = os.path.join(TEMPLATE_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError("找不到模板文件：" + path)
    # 运行后：返回模板文件里的完整文本。
    with open(path, encoding="utf-8") as file_handle:
        return file_handle.read()


def render(template, mapping):
    """把模板里的 {{key}} 替换成 mapping 里 key 对应的值。

    输入：
      template 模板文本；
      mapping  一个字典，例如 {"question": "……", "A": "1", "B": "2"}。
    输出：替换后的文本。
    """
    # 运行前：template 里还有 {{key}} 占位符，例如 "题目：{{question}}"。
    # 运行后：text 变成占位符被替换掉的最终提示词，例如 "题目：使用位填充方法……"。
    text = template
    for key in mapping:
        placeholder = "{{" + key + "}}"
        value = str(mapping[key])
        text = text.replace(placeholder, value)
    return text
