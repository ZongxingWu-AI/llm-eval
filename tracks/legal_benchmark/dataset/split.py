"""项目模块：tracks/legal_benchmark/dataset/split.py。

本文件属于三条评测线或公共工具层的一部分，负责完成本文件名对应的处理步骤。输入来自上游函数或数据目录，输出返回给下游函数或写入对应结果目录。

项目位置：tracks/legal_benchmark/dataset/split.py。
主要用途：法律真实案例 Benchmark，负责判决书解析、结构化提取、出题、校验和法律评测。
输入：输入来自法律线 data/raw、parsed、cleaned、drafts、releases 或 taxonomy/schema。
输出：输出按生命周期写入法律线对应 data 子目录或 results 目录。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：ingestion/extraction/generation/evaluation 可能写文件；只有带模型选项时才调用模型。
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any



def _case_id(row: dict[str, Any]) -> str:
    """读取一条题目或案件记录的案件标识。

    题目优先使用 ``case_id``，兼容旧的中间字段 ``based_on_case`` 和 ``id``。
    返回空字符串表示输入没有可用案件标识；函数只读内存，不写文件。
    """

    value = row.get("case_id")
    if not value:
        value = row.get("based_on_case")
    if not value:
        value = row.get("id")
    return str(value or "")


def _primary_category(row: dict[str, Any]) -> str:
    """读取案件级主分类，供分层抽样使用。

    解析案件使用 ``classification``，正式题目使用 ``case_classification``；
    如果两者都没有，再尝试顶层字段，最终返回“未分类”。
    """

    classification = row.get("classification")
    if not isinstance(classification, dict):
        classification = {}
    case_classification = row.get("case_classification")
    if not isinstance(case_classification, dict):
        case_classification = {}

    value = classification.get("primary_category")
    if not value:
        value = case_classification.get("primary_category")
    if not value:
        value = row.get("primary_category")
    return str(value or "未分类")


def assign_case_splits(rows: list[dict[str, Any]], seed: int = 20260824) -> list[dict[str, Any]]:
    """按案件而不是题目分配 ``dev``、``calibration``、``test``。

    输入是候选题列表；函数先把相同 ``case_id`` 的题目放入同一组，
    再按主分类分层并使用固定随机种子打乱案件顺序。输出是复制后的题目列表，
    每题新增一个 ``split`` 字段，因此同案题目不会跨集合。函数不写文件。
    例如同一案件有三道题，三道题最终会得到相同的 ``split``。
    """
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[_case_id(row)].append(row)

    category_cases: dict[str, list[str]] = defaultdict(list)
    for case_id, group in groups.items():
        category_cases[_primary_category(group[0])].append(case_id)

    rng = random.Random(seed)
    split_by_case: dict[str, str] = {}
    for category in sorted(category_cases):
        case_ids = sorted(category_cases[category])
        rng.shuffle(case_ids)
        count = len(case_ids)
        if count >= 10:
            dev = 3
            calibration = 2
        elif count == 0:
            dev = 0
            calibration = 0
        else:
            dev = max(1, round(count * 0.3))
            calibration = max(0, round(count * 0.2))
            if dev + calibration >= count and count > 1:
                calibration = max(0, count - dev - 1)
        test = count - dev - calibration
        counts = {"dev": dev, "calibration": calibration, "test": test}
        cursor = 0
        for split in ("dev", "calibration", "test"):
            for case_id in case_ids[cursor:cursor + counts[split]]:
                split_by_case[case_id] = split
            cursor += counts[split]

    result: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        copy["split"] = split_by_case.get(_case_id(copy), "dev")
        result.append(copy)
    return result
