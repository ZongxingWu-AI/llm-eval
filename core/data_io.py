"""公共 JSONL 数据读写模块。

输入是一行一个 JSON 对象的文件路径或字典列表，输出是字典列表或写入后的 Path。
C-Eval、Pairwise Judge 和法律线都通过本模块统一读写 JSONL，避免重复实现格式细节。
读取只访问指定文件；写入会创建父目录并覆盖目标文件，不调用模型。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """用途：读取一行一个 JSON 对象的 JSONL 文件。

    输入：path：JSONL 文件路径，空行允许存在。
    输出：按文件顺序返回字典列表。
    运行前数据形态：磁盘上是多行独立 JSON 对象。
    运行后数据变化：每个非空行经 json.loads 变成一个字典。
    副作用：只读文件，不修改内容、不调用模型。
    异常或失败处理：文件不存在或某行 JSON 非法时向上抛出异常。
    最小示例：两行对象会得到两个字典组成的列表。"""

    rows: list[dict[str, Any]] = []
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for line in lines:
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    """用途：把字典序列写成一行一个对象的 JSONL。

    输入：path：目标路径；rows：字典可迭代对象。
    输出：返回 None，数据写入目标文件。
    运行前数据形态：内存中是字典列表或生成器。
    运行后数据变化：每个字典序列化为一行，不添加外层数组。
    副作用：创建父目录并覆盖同名文件；不调用模型。
    异常或失败处理：值不可序列化或路径不可写时向上抛出异常。
    最小示例：输入两个字典会写成两行 JSON。"""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for row in rows:
        lines.append(json.dumps(row, ensure_ascii=False))
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
