"""Pairwise Judge 路径常量模块。

根据包位置提供 data、prompts 和 results 的 Path 常量，供生成、裁判和报告模块使用。
导入只计算路径，不创建目录、不调用模型。"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
TRACK_ROOT = _ROOT / "tracks" / "pairwise_judge"
DATA_ROOT = TRACK_ROOT / "data"

PROMPT_ROOT = TRACK_ROOT / "prompts"
RESULTS_ROOT = TRACK_ROOT / "results"
