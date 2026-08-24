"""项目模块：tracks/pairwise_judge/judge_prompt.py。

本文件属于三条评测线或公共工具层的一部分，负责完成本文件名对应的处理步骤。输入来自上游函数或数据目录，输出返回给下游函数或写入对应结果目录。

项目位置：tracks/pairwise_judge/judge_prompt.py。
主要用途：开放题 LLM-as-Judge 评测线，负责生成回答、位置交换裁判、多裁判统计和报告。
输入：输入来自本评测线的 data 目录、裁判 Prompt 和公共模型客户端。
输出：输出写入本评测线的 results 目录，供偏见分析和报告阅读。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：生成和裁判模块会调用模型；统计和报告模块只处理内存数据或写结果文件。
"""

from core import prompt_loader


def build_judge_prompt(question: str, answer_a: str, answer_b: str) -> str:
    """把题目和两份回答填入裁判 Prompt 模板。

    输入是题干、回答 A 和回答 B；输出是可直接发送给裁判模型的完整文本。
    函数只读取 Prompt 文件，不调用模型、不写结果文件。
    """

    template_dir = prompt_loader.PROJECT_ROOT / "tracks" / "pairwise_judge" / "prompts"
    template = prompt_loader.load_template("judge_prompt.md", template_dir)
    rubric = prompt_loader.load_template("judge_rubric.md", template_dir)
    return prompt_loader.render(
        template,
        {"question": question, "answer_a": answer_a, "answer_b": answer_b, "rubric": rubric},
    )
