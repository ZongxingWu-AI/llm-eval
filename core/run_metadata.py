"""公共运行元数据模块：负责生成时间戳和运行记录。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def new_run_metadata(track: str, **extra: Any) -> dict[str, Any]:
    """创建一次运行记录的基础元数据。调用后返回包含 track、时间和调用参数的字典，供结果目录中的 run_metadata.json 保存。"""

    metadata = {
        "track": track,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata.update(extra)
    return metadata


def timestamped_run_dir(base_dir: str | Path) -> Path:
    """在结果根目录下创建带时间戳的运行目录。调用前是结果根目录，调用后返回新目录路径并确保目录已经存在。"""

    path = Path(base_dir) / datetime.now().strftime("%Y%m%d_%H%M%S")
    path.mkdir(parents=True, exist_ok=True)
    return path
