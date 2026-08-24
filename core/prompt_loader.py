"""公共 Prompt 加载模块：负责读取模板并替换占位符。"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_VAR_PATTERN = r"{{\s*([A-Za-z0-9_]+)\s*}}"


def load_template(name: str, template_dir: str | Path | None = None) -> str:
    """从指定 Prompt 目录读取 Markdown 模板。调用前提供文件名和可选目录，调用后返回完整模板文本，文件不存在时抛出 FileNotFoundError。"""

    directory = Path(template_dir) if template_dir else PROJECT_ROOT
    if not template_dir:
        matches = list(directory.glob(f"tracks/*/prompts/{name}"))
    else:
        matches = [directory / name]
    if not matches or not matches[0].is_file():
        raise FileNotFoundError(f"template not found: {name}")
    return matches[0].read_text(encoding="utf-8")


def render(template: str, mapping: Mapping[str, object]) -> str:
    """替换 Prompt 模板中的占位符。调用前是模板字符串和字段映射，调用后是可以直接发送给模型的完整 Prompt。"""

    text = template
    for key, value in mapping.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text
