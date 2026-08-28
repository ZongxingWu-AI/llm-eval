"""法律真实案例 Benchmark 的公共路径注册表。

本文件服务于当前仓库的四个教学环节：造 Benchmark、构建题集、模型作答和结果评测。
它只计算法律项目内部的代码、数据、Prompt、Taxonomy、Schema 和结果目录，
不导入其他评测项目的业务代码。
本模块不读取数据、不调用模型、不创建目录。
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
METHODOLOGY_ROOT = PROJECT_ROOT / "methodology"

BENCHMARK_ROOT = METHODOLOGY_ROOT / "01_造Benchmark"
QUESTION_SET_ROOT = METHODOLOGY_ROOT / "02_构建题集"
ANSWER_ROOT = METHODOLOGY_ROOT / "03_模型作答"
SCORING_ROOT = METHODOLOGY_ROOT / "04_结果评测"

LEGAL_ROOT = BENCHMARK_ROOT / "legal"
LEGAL_DATA_ROOT = LEGAL_ROOT / "data"
LEGAL_PROMPT_ROOT = LEGAL_ROOT / "prompts"
LEGAL_RESULTS_ROOT = LEGAL_ROOT / "results"
LEGAL_TAXONOMY_ROOT = LEGAL_ROOT / "taxonomy"
LEGAL_SCHEMA_ROOT = LEGAL_ROOT / "schemas"
