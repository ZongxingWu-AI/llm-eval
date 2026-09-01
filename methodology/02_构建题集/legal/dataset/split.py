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


def _split_counts(count: int, split_ratios: dict[str, float]) -> dict[str, int]:
    """把案件数量按比例转换成整数 split 配额。"""
    if count <= 0:
        return {str(key): 0 for key in split_ratios}
    cleaned = {str(key): max(0.0, float(value)) for key, value in split_ratios.items()}
    total_ratio = sum(cleaned.values())
    if total_ratio <= 0:
        raise ValueError("split_ratios 至少需要一个正数比例")
    raw = {key: count * value / total_ratio for key, value in cleaned.items()}
    result = {key: int(value) for key, value in raw.items()}
    remainder = count - sum(result.values())
    ranked = sorted(
        raw,
        key=lambda key: (raw[key] - result[key], -list(raw).index(key)),
        reverse=True,
    )
    for key in ranked[:remainder]:
        result[key] += 1
    return result


def assign_case_splits(
    rows: list[dict[str, Any]],
    seed: int = 20260824,
    split_ratios: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """按案件分组并按主分类和比例分配 dev、calibration、test。

    输入：rows 是案件或问题字典列表；seed 控制稳定随机顺序；split_ratios 控制案件级比例。
    输出：返回逐行浅拷贝的新列表，每行新增或统一 split 字段。
    运行前数据形态：运行前同案多题可能尚无固定 split。
    运行后数据变化：运行后同一 case_id 的全部题共享一个 split，固定 seed 可重复。
    副作用：只处理内存，不写文件、不调用模型，也不修改输入字典。
    异常或失败处理：缺 case_id 的行会作为同一空标识组；比例为空或全为零时抛出明确错误。
    最小示例：十个案件按默认 20%/20%/60% 得到 2/2/6。"""
    ratios = split_ratios or {"dev": 0.2, "calibration": 0.2, "test": 0.6}
    if not isinstance(ratios, dict) or not ratios:
        raise ValueError("split_ratios 必须是非空字典")
    if any(float(value) < 0 for value in ratios.values()):
        raise ValueError("split_ratios 不能包含负数")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[_case_id(row)].append(row)

    category_cases: dict[str, list[str]] = defaultdict(list)
    for case_id, group in groups.items():
        category_cases[_primary_category(group[0])].append(case_id)

    rng = random.Random(seed)
    split_by_case: dict[str, str] = {}
    split_names = tuple(str(key) for key in ratios)
    for category in sorted(category_cases):
        case_ids = sorted(category_cases[category])
        rng.shuffle(case_ids)
        counts = _split_counts(len(case_ids), {str(key): float(value) for key, value in ratios.items()})
        cursor = 0
        for split in split_names:
            size = counts.get(split, 0)
            for case_id in case_ids[cursor:cursor + size]:
                split_by_case[case_id] = split
            cursor += size

    fallback = split_names[0] if split_names else "dev"
    result: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        copy["split"] = split_by_case.get(_case_id(copy), fallback)
        result.append(copy)
    return result

