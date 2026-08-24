"""法律 Benchmark 路径常量模块。

根据包目录提供 data、prompts、schemas、taxonomy 和 results 等 Path 常量。
所有法律子模块通过这里定位自己的文件，避免写入其他评测线。
导入只计算路径，不创建目录、不调用模型。"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
TRACK_ROOT = _ROOT / "tracks" / "legal_benchmark"
LEGAL_ROOT = TRACK_ROOT

DATA_ROOT = LEGAL_ROOT / "data"
PROMPT_ROOT = LEGAL_ROOT / "prompts"
RESULTS_ROOT = LEGAL_ROOT / "results"
TAXONOMY_ROOT = LEGAL_ROOT / "taxonomy"
SCHEMA_ROOT = LEGAL_ROOT / "schemas"
