"""法律题型的结构化契约校验。

题型决定“怎么测”，法律维度决定“测什么”。本模块只校验题型层，
不在这里重复维度或评分语义。
"""
from __future__ import annotations

import math
import re
from typing import Any

DEFAULT_SCORING = {
    "single_choice": "rule",
    "multiple_choice": "rule",
    "true_false": "rule",
    "numeric": "rule",
    "structured_extraction": "rule",
    "short_answer": "rubric_judge",
    "case_analysis": "rubric_judge",
    "legal_drafting": "rubric_judge",
    "compliance_response": "redline",
}
EXPECTED_ANSWER_TYPE = {
    "single_choice": "选项",
    "multiple_choice": "选项集合",
    "true_false": "判断",
    "numeric": "金额",
    "structured_extraction": "结构化数据",
    "short_answer": "结构化论述",
    "case_analysis": "结构化论述",
    "legal_drafting": "法律文本",
    "compliance_response": "拒答与替代建议",
}
_CHOICE_ID_RE = re.compile(r"^[A-Z]$")


def _options(row: dict[str, Any]) -> list[dict[str, Any]]:
    """读取题目的选项对象；非列表或非对象项会被忽略，交由上层报结构错误。"""
    value = row.get("options")
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    """把字符串或序列标准化为非空字符串列表。"""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def validate_question_format(row: dict[str, Any]) -> list[str]:
    """返回题型字段错误；合法题型返回空列表。"""
    fmt = str(row.get("question_format") or "").strip()
    if not fmt:
        return ["缺少 question_format"]
    if fmt not in DEFAULT_SCORING:
        return [f"无效 question_format: {fmt}"]
    issues: list[str] = []
    expected_method = DEFAULT_SCORING[fmt]
    if row.get("scoring_method") != expected_method:
        issues.append(f"question_format 与 scoring_method 不匹配: {fmt} -> {expected_method}")
    expected_answer = EXPECTED_ANSWER_TYPE[fmt]
    if row.get("answer_type") and row.get("answer_type") != expected_answer:
        issues.append(f"question_format 与 answer_type 不匹配: {fmt} -> {expected_answer}")

    if fmt in {"single_choice", "multiple_choice"}:
        opts = _options(row)
        if len(opts) != 4:
            issues.append(f"{fmt} 必须有 4 个选项")
        ids = [str(item.get("option_id") or "").strip() for item in opts]
        texts = [str(item.get("text") or "").strip() for item in opts]
        if any(not item for item in ids + texts):
            issues.append("选项必须包含非空 option_id 和 text")
        if len(set(ids)) != len(ids):
            issues.append("选项 ID 必须唯一")
        if any(not _CHOICE_ID_RE.fullmatch(item) for item in ids if item):
            issues.append("选项 ID 必须使用单个大写字母")
        if len(set(texts)) != len(texts):
            issues.append("选项文本不能重复")
        if fmt == "single_choice":
            correct = str(row.get("correct_option") or "").strip()
            if correct not in ids or ids.count(correct) != 1:
                issues.append("单选题必须有一个有效且唯一的 correct_option")
            if isinstance(row.get("correct_options"), list):
                issues.append("单选题不应设置 correct_options")
        else:
            correct = _string_list(row.get("correct_options"))
            if len(correct) < 2 or len(correct) >= len(ids) or not set(correct) <= set(ids):
                issues.append("多选题正确选项必须至少 2 项、少于全部选项且属于 options")
            if row.get("correct_option") is not None:
                issues.append("多选题不应设置 correct_option")
        if "distractor" not in set(_string_list(row.get("sample_tags"))):
            issues.append("选择题缺少 distractor 标签")
        rationales = row.get("distractor_rationales")
        if not isinstance(rationales, dict):
            issues.append("选择题缺少 distractor_rationales")
        else:
            correct_ids = {str(row.get("correct_option"))} if fmt == "single_choice" else set(_string_list(row.get("correct_options")))
            for option_id in ids:
                if option_id not in correct_ids and not str(rationales.get(option_id) or "").strip():
                    issues.append(f"干扰项 {option_id} 缺少错误依据")
    elif fmt == "true_false":
        value = row.get("correct_answer")
        if not isinstance(value, bool) and str(value).lower() not in {"true", "false", "是", "否", "正确", "错误"}:
            issues.append("判断题 correct_answer 必须是 true/false 或明确中文值")
    elif fmt == "numeric":
        value = row.get("numeric_answer")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            issues.append("数值题 numeric_answer 必须是有限数值")
        if not str(row.get("numeric_unit") or "").strip():
            issues.append("数值题缺少 numeric_unit")
        if row.get("numeric_tolerance") is not None:
            tolerance = row.get("numeric_tolerance")
            if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or float(tolerance) < 0:
                issues.append("numeric_tolerance 必须是非负数")
        if not _string_list(row.get("calculation_steps")):
            issues.append("数值题缺少 calculation_steps")
    elif fmt == "structured_extraction":
        if row.get("structured_answer") is None and row.get("reference_answer") is None:
            issues.append("结构化抽取题缺少 structured_answer")
    elif fmt in {"short_answer", "case_analysis", "legal_drafting"}:
        if not isinstance(row.get("answer_requirements"), dict) or not row.get("answer_requirements"):
            issues.append("开放题缺少 answer_requirements")
        if not isinstance(row.get("rubric"), dict) or not row.get("rubric"):
            issues.append("开放题缺少 rubric")
        if fmt == "case_analysis":
            req = row.get("answer_requirements") or {}
            if req.get("must_include_conclusion") is not True:
                issues.append("案例分析题必须要求结论")
            if req.get("must_include_legal_basis") is not True:
                issues.append("案例分析题必须要求法律依据")
    elif fmt == "compliance_response":
        req = row.get("answer_requirements") or {}
        if not isinstance(req, dict) or req.get("must_refuse") is not True:
            issues.append("合规题必须要求拒绝不当请求")
        if not isinstance(req, dict) or not req.get("must_offer_alternative", True):
            issues.append("合规题必须要求合法替代建议")
    return list(dict.fromkeys(issues))


def validate_pairs(rows: list[dict[str, Any]]) -> list[str]:
    """校验 minimal_pair/counterfactual 的成对约束。"""
    groups: dict[str, list[dict[str, Any]]] = {}
    issues: list[str] = []
    for row in rows:
        pair_id = str(row.get("pair_id") or "").strip()
        role = str(row.get("pair_role") or "").strip()
        tagged = {str(x) for x in row.get("sample_tags", []) or []}
        if pair_id or role or "minimal_pair" in tagged or "counterfactual" in tagged:
            if not pair_id or role not in {"base", "counterfactual"}:
                issues.append(f"{row.get('question_id', '')}: pair_id/pair_role 不完整")
            else:
                groups.setdefault(pair_id, []).append(row)
    for pair_id, members in groups.items():
        roles = [str(item.get("pair_role")) for item in members]
        if len(members) != 2 or sorted(roles) != ["base", "counterfactual"]:
            issues.append(f"pair_id {pair_id} 必须恰好包含 base 和 counterfactual 各一题")
        if any("counterfactual" not in set(item.get("sample_tags", []) or []) for item in members):
            issues.append(f"pair_id {pair_id} 的题目必须带 counterfactual 标签")
    return issues


__all__ = ["DEFAULT_SCORING", "EXPECTED_ANSWER_TYPE", "validate_question_format", "validate_pairs"]