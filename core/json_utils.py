"""公共模型 JSON 解析模块。

输入可能是纯 JSON、Markdown 代码围栏或夹杂解释文字的模型响应。
输出是解析后的任意 JSON 值或字典，并通过平衡括号扫描寻找候选片段。
本模块供裁判、法律提取和评分共用，只处理内存，不写文件、不调用模型。"""

from __future__ import annotations

import json
import re
from typing import Any


def _balanced_candidates(text: str, opening: str, closing: str) -> list[str]:
    """用途：扫描解释文本中括号平衡的 JSON 对象或数组候选。

    输入：text：模型原始文本；opening/closing：起止括号。
    输出：按出现顺序返回候选字符串列表。
    运行前数据形态：文本可能含说明文字、字符串内括号和多个 JSON。
    运行后数据变化：只在字符串外更新深度，深度回到零时截取候选。
    副作用：只处理内存，不调用模型、不写文件。
    异常或失败处理：没有完整闭合片段时返回空列表。
    最小示例：输入 x {"a":"}"} y 仍会返回完整对象。"""

    candidates: list[str] = []
    for start, char in enumerate(text):
        if char != opening:
            continue
        # depth 是尚未闭合的括号层数。
        depth = 0
        # 字符串内容中的括号不能影响 JSON 结构深度。
        in_string = False
        # escaped 用来区分真正的引号和 \" 转义引号。
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
    """用途：从纯 JSON、Markdown 围栏或混杂文本提取首个有效对象或数组。

    输入：text：模型原始字符串。
    输出：返回 dict 或 list。
    运行前数据形态：输入可能有前后解释和多个候选。
    运行后数据变化：依次尝试整段、围栏、对象片段和数组片段。
    副作用：只处理内存，不调用模型、不写文件。
    异常或失败处理：非字符串或无合法 JSON 时抛出 ValueError。
    最小示例：围栏中的 {"winner":"A"} 会返回字典。"""
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
    """用途：要求模型文本最终解析为 JSON 对象。

    输入：text：可能带围栏或解释的模型文本。
    输出：返回 dict。
    运行前数据形态：输入仍是未解析字符串。
    运行后数据变化：先调用 parse_json_value，再检查返回类型。
    副作用：只处理内存，不调用模型、不写文件。
    异常或失败处理：无法解析或结果是数组等非对象时抛出 ValueError。
    最小示例：输入 [1,2] 会报错。"""
    value = parse_json_value(text)
    if not isinstance(value, dict):
        raise ValueError("model output JSON must be an object")
    return value
