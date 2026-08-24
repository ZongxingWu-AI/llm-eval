"""路径配置模块：tracks/legal_benchmark/paths.py。

本文件集中定义当前评测线的数据、Prompt、结果和 schema 路径。其他模块通过这些常量读写文件，避免各处重复拼接路径。

项目位置：tracks/legal_benchmark/paths.py。
主要用途：法律真实案例 Benchmark，负责判决书解析、结构化提取、出题、校验和法律评测。
输入：输入来自法律线 data/raw、parsed、cleaned、drafts、releases 或 taxonomy/schema。
输出：输出按生命周期写入法律线对应 data 子目录或 results 目录。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：ingestion/extraction/generation/evaluation 可能写文件；只有带模型选项时才调用模型。
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
TRACK_ROOT = _ROOT / "tracks" / "legal_benchmark"
LEGAL_ROOT = TRACK_ROOT

DATA_ROOT = LEGAL_ROOT / "data"
PROMPT_ROOT = LEGAL_ROOT / "prompts"
RESULTS_ROOT = LEGAL_ROOT / "results"
TAXONOMY_ROOT = LEGAL_ROOT / "taxonomy"
SCHEMA_ROOT = LEGAL_ROOT / "schemas"
