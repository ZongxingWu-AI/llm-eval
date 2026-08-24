"""法律题集案件级划分模块。

项目位置：dataset.build 使用的纯内存辅助模块。
输入：包含 case_id 与案件主分类的候选题或正式题目列表。
输出：为每条复制记录增加 dev、calibration 或 test 的 split 字段。
上下游：由题集组装调用，结果随后进入正式 release 和验证阶段。
副作用：不读写数据文件、不调用模型；使用固定随机种子保证重复运行一致。"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any



def _case_id(row: dict[str, Any]) -> str:
    """用途：从题目或案件记录中读取兼容的案件标识。

    输入：row 可能含 case_id、based_on_case 或 id。
    输出：返回字符串案件标识；都缺失时返回空字符串。
    运行前数据形态：输入字段命名可能来自不同管道阶段。
    运行后数据变化：输出统一为分组所需 case_id。
    副作用：只读字典，不写文件、不调用模型。
    异常或失败处理：空值按兼容顺序回退，最终返回空字符串。"""

    value = row.get("case_id")
    if not value:
        value = row.get("based_on_case")
    if not value:
        value = row.get("id")
    return str(value or "")


def _primary_category(row: dict[str, Any]) -> str:
    """用途：从解析案件或正式题目的分类对象中读取主分类。

    输入：row 可能含 classification、case_classification 或顶层 primary_category。
    输出：返回主分类字符串；均缺失时返回“未分类”。
    运行前数据形态：运行前不同阶段分类字段位置不同。
    运行后数据变化：运行后得到统一分层键。
    副作用：只读字典，不写文件、不调用模型。
    异常或失败处理：分类字段类型错误时忽略该来源并继续回退。"""

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
    """用途：按 case_id 分组并按主分类分层分配 dev、calibration、test。

    输入：rows 是案件或问题字典列表；seed 控制稳定随机顺序。
    输出：返回逐行浅拷贝的新列表，每行新增或统一 split。
    运行前数据形态：运行前同案多题尚无固定 split。
    运行后数据变化：运行后同一 case_id 的全部题共享一个 split，固定 seed 可重复。
    副作用：只处理内存，不写文件、不调用模型，也不修改输入字典。
    异常或失败处理：缺 case_id 的行会作为同一空标识组；小样本按比例回退，十案及以上按 3/2/其余分配。
    最小示例：某分类十个案件会得到 3 dev、2 calibration、5 test。"""
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
