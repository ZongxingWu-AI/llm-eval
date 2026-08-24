"""公共 Prompt 模板加载模块。

输入是模板文件名、模板目录和占位符字典，输出是模板文本或完成替换的 Prompt。
三条评测线只共享加载和渲染机制，具体 Prompt 仍放在各自 prompts 目录。
本模块读取文本文件，不写文件、不调用模型。"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_VAR_PATTERN = r"{{\s*([A-Za-z0-9_]+)\s*}}"


def load_template(name: str, template_dir: str | Path | None = None) -> str:
    """用途：从指定评测线 prompts 目录读取 Markdown 模板。

    输入：name：模板名；template_dir：可选目录。
    输出：返回 UTF-8 模板全文。
    副作用：读取文件，不写文件、不调用模型。
    异常或失败处理：找不到模板时抛出 FileNotFoundError。"""

    directory = Path(template_dir) if template_dir else PROJECT_ROOT
    if not template_dir:
        matches = list(directory.glob(f"tracks/*/prompts/{name}"))
    else:
        matches = [directory / name]
    if not matches or not matches[0].is_file():
        raise FileNotFoundError(f"template not found: {name}")
    return matches[0].read_text(encoding="utf-8")


def render(template: str, mapping: Mapping[str, object]) -> str:
    """用途：替换 Prompt 中的双花括号占位符。

    输入：template：模板文本；mapping：字段映射。
    输出：返回渲染后的新字符串。
    副作用：只处理内存，不调用模型、不写文件。
    异常或失败处理：未提供映射的占位符原样保留。"""

    text = template
    for key, value in mapping.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text
