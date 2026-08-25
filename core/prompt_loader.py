"""公共 Prompt 模板加载模块。

输入是模板文件名、可选模板目录和占位符字典，输出是模板全文或完成替换的 Prompt。
三条评测线共享同一套加载与渲染机制，但模板文件仍保存在各自的 prompts 目录。
本模块只读取 UTF-8 文本，不写文件、不调用模型，也不修改环境变量。
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_VAR_PATTERN = r"{{\s*([A-Za-z0-9_]+)\s*}}"


def load_template(name: str, template_dir: str | Path | None = None) -> str:
    """用途：读取指定名称的 Prompt Markdown 模板。

    输入：
        name 是模板文件名，例如 ``ceval_prompt.md``；template_dir 是可选目录。
        传入目录时只在该目录中查找；不传目录时扫描四大方法论技术包下的 prompts 目录。
    输出：
        返回 UTF-8 模板全文字符串。
    运行前数据形态：
        调用方只有模板名，或已经知道模板所在目录。
    运行后数据变化：
        模板文件内容被读入内存，磁盘文件保持不变。
    副作用：
        读取一个文本文件；不写文件、不调用模型、不创建目录。
    异常或失败处理：
        没有找到模板时抛出 FileNotFoundError；同名模板存在多个时按路径排序取第一个。
    最小示例：
        ``load_template("ceval_prompt.md", PROMPT_ROOT)`` 返回 C-Eval Prompt 全文。
    """

    matches: list[Path] = []

    if template_dir is not None:
        directory = Path(template_dir)
        matches.append(directory / name)
    else:
        pattern = f"methodology/*/*/prompts/{name}"
        for candidate in PROJECT_ROOT.glob(pattern):
            matches.append(candidate)
        matches.sort()

    if not matches:
        raise FileNotFoundError(f"template not found: {name}")

    template_path = matches[0]
    if not template_path.is_file():
        raise FileNotFoundError(f"template not found: {name}")

    return template_path.read_text(encoding="utf-8")


def render(template: str, mapping: Mapping[str, object]) -> str:
    """用途：把 Prompt 中的双花括号占位符替换为实际值。

    输入：template 是模板文本；mapping 是“占位符名称 -> 实际值”的映射。
    输出：返回替换后的新字符串。
    运行前数据形态：例如 ``题目：{{question}}`` 和 ``{"question": "1+1?"}``。
    运行后数据变化：对应占位符变为 ``题目：1+1?``，原始 template 不会被修改。
    副作用：只处理内存，不写文件、不调用模型。
    异常或失败处理：mapping 中没有提供的占位符会原样保留。
    """

    text = template
    for key, value in mapping.items():
        placeholder = "{{" + key + "}}"
        text = text.replace(placeholder, str(value))
    return text
