"""路径配置模块：tracks/ceval/paths.py。

本文件集中定义当前评测线的数据、Prompt、结果和 schema 路径。其他模块通过这些常量读写文件，避免各处重复拼接路径。

项目位置：tracks/ceval/paths.py。
主要用途：C-Eval 客观题评测线，负责题目获取、模型作答和客观准确率统计。
输入：输入来自本评测线的 data 目录、公共模型客户端和 Prompt。
输出：输出写入本评测线的 results 目录，供准确率汇总和报告使用。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：fetch 可能访问数据源；evaluate 会调用模型并写评测结果。
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
TRACK_ROOT = _ROOT / "tracks" / "ceval"
DATA_ROOT = TRACK_ROOT / "data"

PROMPT_ROOT = TRACK_ROOT / "prompts"
RESULTS_ROOT = TRACK_ROOT / "results"
