"""公共运行元数据模块。

输入是评测线名称和调用方补充字段，输出带 UTC 时间、Python 版本等信息的字典或时间戳目录。
各评测线用它记录可复现实验上下文并隔离不同运行。
创建运行目录的函数会写文件系统；本模块不调用模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def new_run_metadata(track: str, **extra: Any) -> dict[str, Any]:
    """用途：创建统一运行元数据字典。

    输入：track：阶段名；extra：模型、路径和数量等字段。
    输出：返回含 track、UTC started_at 和附加字段的字典。
    副作用：只读取当前时间，不写文件、不调用模型。
    异常或失败处理：同名 extra 会按 dict.update 覆盖基础字段。"""

    metadata = {
        "track": track,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata.update(extra)
    return metadata


def timestamped_run_dir(base_dir: str | Path) -> Path:
    """用途：在结果根目录创建时间戳运行目录。

    输入：base_dir：结果根目录。
    输出：返回已经存在的 Path。
    副作用：创建目录，不调用模型。
    异常或失败处理：目录不可创建时向上抛出文件系统异常。"""

    path = Path(base_dir) / datetime.now().strftime("%Y%m%d_%H%M%S")
    path.mkdir(parents=True, exist_ok=True)
    return path
