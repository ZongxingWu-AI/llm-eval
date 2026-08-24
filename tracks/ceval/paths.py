"""C-Eval 路径常量模块。

根据当前文件位置计算评测线根目录、data、prompts 和 results 路径，供 fetch/evaluate 共用。
输入仅为项目目录结构，输出是 Path 常量；导入时不创建目录、不调用模型。"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
TRACK_ROOT = _ROOT / "tracks" / "ceval"
DATA_ROOT = TRACK_ROOT / "data"

PROMPT_ROOT = TRACK_ROOT / "prompts"
RESULTS_ROOT = TRACK_ROOT / "results"
