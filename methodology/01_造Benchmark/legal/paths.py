"""法律 Benchmark 的路径常量。

法律原始案例、解析结果、结构化结果、候选题、正式题集、Prompt、Schema、
Taxonomy 和评测结果都集中在 01_造Benchmark/legal 下。代码模块从
core.project_paths 读取真实路径；本文件保留法律线易读的本地别名。
"""

from core.project_paths import LEGAL_DATA_ROOT as DATA_ROOT
DATASETS_ROOT = DATA_ROOT / "datasets"
from core.project_paths import LEGAL_PROMPT_ROOT as PROMPT_ROOT
from core.project_paths import LEGAL_RESULTS_ROOT as RESULTS_ROOT
from core.project_paths import LEGAL_SCHEMA_ROOT as SCHEMA_ROOT
from core.project_paths import LEGAL_ROOT
from core.project_paths import LEGAL_TAXONOMY_ROOT as TAXONOMY_ROOT

