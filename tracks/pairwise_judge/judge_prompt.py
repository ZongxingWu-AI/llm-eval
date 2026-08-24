"""Pairwise 裁判 Prompt 组装模块。

输入是一道开放题及两个候选回答，输出按裁判模板渲染的 Prompt。
第二轮由调用方交换回答位置，本模块不判断胜负。
只读取 prompts 模板并处理字符串，不写文件、不调用模型。"""

from core import prompt_loader


def build_judge_prompt(question: str, answer_a: str, answer_b: str) -> str:
    """用途：把问题和当前位置 A/B 回答填入裁判 Prompt。

    输入：question、answer_a、answer_b。
    输出：返回完整裁判 Prompt。
    副作用：读取模板，不调用模型、不写文件。
    异常或失败处理：模板不存在时向上抛出异常。"""

    template_dir = prompt_loader.PROJECT_ROOT / "tracks" / "pairwise_judge" / "prompts"
    template = prompt_loader.load_template("judge_prompt.md", template_dir)
    rubric = prompt_loader.load_template("judge_rubric.md", template_dir)
    return prompt_loader.render(
        template,
        {"question": question, "answer_a": answer_a, "answer_b": answer_b, "rubric": rubric},
    )
