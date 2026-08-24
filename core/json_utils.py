"""公共 JSON 解析模块：负责从模型文本中提取 JSON，不写文件。"""

from __future__ import annotations

import json
import re
from typing import Any


def _balanced_candidates(text: str, opening: str, closing: str) -> list[str]:
    """为同一文件中的公开流程提供一个小而明确的辅助步骤。

参数：text、opening、closing。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    candidates: list[str] = []
    for start, char in enumerate(text):
        if char != opening:
            continue
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            current = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current == opening:
                depth += 1
            elif current == closing:
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:index + 1])
                    break
    return candidates


def parse_json_value(text: str) -> Any:
    """从模型输出中提取第一个有效的 JSON 对象或数组。

    输入：text 是模型原始文本，可以是纯 JSON、Markdown JSON 围栏，
    也可以是“解释文字 + JSON”的混合文本。
    输出：返回 Python 字典或列表。
    运行前数据形态：文本可能包含前后说明、多个候选片段或转义字符串。
    运行后数据变化：先尝试整段文本，再尝试围栏和括号平衡片段，最后把有效片段反序列化。
    副作用：不写文件、不调用模型；找不到有效 JSON 时抛出 ValueError。
    异常或失败处理：非字符串输入或所有候选都无法解析时明确抛出 ValueError。
    最小示例：输入“答案如下：```json
{\"winner\": \"A\"}
```”，输出 `{"winner": "A"}` 对应的字典。
    """
    if not isinstance(text, str):
        raise ValueError("model output must be a string")

    candidates: list[str] = []
    stripped = text.strip()
    if stripped:
        candidates.append(stripped)

    fenced_pattern = r"\x60\x60\x60(?:json)?\s*([\[{].*?[\]}])\s*\x60\x60\x60"
    fenced_values = re.findall(fenced_pattern, text, flags=re.IGNORECASE | re.DOTALL)
    candidates.extend(fenced_values)
    candidates.extend(_balanced_candidates(text, "{", "}"))
    candidates.extend(_balanced_candidates(text, "[", "]"))

    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(value, (dict, list)):
            return value
    raise ValueError("no valid JSON object or array found in model output")


def parse_json_object(text: str) -> dict[str, Any]:
    """解析并校验模型输出必须是 JSON 对象。它复用 parse_json_value，拒绝数组和基础类型。"""
    value = parse_json_value(text)
    if not isinstance(value, dict):
        raise ValueError("model output JSON must be an object")
    return value
