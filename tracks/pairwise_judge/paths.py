"""路径配置模块：tracks/pairwise_judge/paths.py。

本文件集中定义当前评测线的数据、Prompt、结果和 schema 路径。其他模块通过这些常量读写文件，避免各处重复拼接路径。

项目位置：tracks/pairwise_judge/paths.py。
主要用途：开放题 LLM-as-Judge 评测线，负责生成回答、位置交换裁判、多裁判统计和报告。
输入：输入来自本评测线的 data 目录、裁判 Prompt 和公共模型客户端。
输出：输出写入本评测线的 results 目录，供偏见分析和报告阅读。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：生成和裁判模块会调用模型；统计和报告模块只处理内存数据或写结果文件。
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
TRACK_ROOT = _ROOT / "tracks" / "pairwise_judge"
DATA_ROOT = TRACK_ROOT / "data"

PROMPT_ROOT = TRACK_ROOT / "prompts"
RESULTS_ROOT = TRACK_ROOT / "results"
