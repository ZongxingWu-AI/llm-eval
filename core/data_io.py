"""公共数据读写模块：提供 JSONL 文件的读取和写入，不调用模型。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """读取一个 JSONL 文件，并把它变成字典列表。

    参数：
        path：JSONL 文件路径。文件约定为“一行一个 JSON 对象”，空行会跳过。
    返回：
        按文件原顺序排列的字典列表。
    副作用：
        只读文件，不修改文件内容。若 JSON 格式错误，``json.loads`` 会抛出异常，
        让上游知道输入文件需要修复。
    数据变化示例：
        文件内容 ``{"id": "q1"}\n{"id": "q2"}``，调用后得到
        ``[{"id": "q1"}, {"id": "q2"}]``。
    """

    rows: list[dict[str, Any]] = []
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for line in lines:
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    """把字典序列写成 JSONL 文件。

    参数：
        path：目标 JSONL 路径。父目录不存在时会自动创建。
        rows：字典列表或其他可迭代对象。
    返回：
        ``None``。数据通过文件写入落盘。
    副作用：
        会创建父目录并覆盖同名目标文件；不会修改传入的字典。
    数据变化示例：
        输入 ``[{"id": "q1"}, {"id": "q2"}]`` 会写成两行，
        而不是写成一个外层数组 ``[...]``。
    """

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for row in rows:
        lines.append(json.dumps(row, ensure_ascii=False))
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
