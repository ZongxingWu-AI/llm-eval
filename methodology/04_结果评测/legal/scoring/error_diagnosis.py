"""法律回答错误诊断。

诊断只解释已有评分结果，不改变 PASS/REVIEW/REJECT 判定，也不把裁判调用失败误记为模型能力错误。
"""
from __future__ import annotations

import importlib
from typing import Any

_config = importlib.import_module("methodology.02_构建题集.legal.config")


def _known_errors() -> set[str]:
    """加载错误分类目录中的合法错误标签。"""
    try:
        data = _config.load_error_taxonomy()
        errors = data.get("errors", {}) if isinstance(data, dict) else {}
        return {str(key) for key in errors}
    except Exception:
        return {
            "factual_omission", "factual_hallucination", "entity_confusion", "issue_missed",
            "rule_misapplication", "element_omission", "statute_hallucination",
            "similar_concept_confusion", "evidence_overclaim", "burden_of_proof_error",
            "causation_error", "temporal_error", "amount_calculation_error",
            "unsupported_conclusion", "counterargument_omission", "instruction_failure",
            "format_error", "refusal_failure", "over_refusal", "privacy_leak",
            "uncertainty_failure",
        }


def _as_tags(value: Any, known: set[str]) -> list[str]:
    """把裁判输出中的错误标签标准化并过滤未知值。"""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item) for item in value if str(item) in known]


def diagnose_errors(
    row: dict[str, Any],
    answer: str,
    scoring: dict[str, Any] | None,
) -> dict[str, Any]:
    """根据规则评分或 Rubric Judge 结果生成可解释的错误标签。

    裁判/解析失败时返回空标签和 ``diagnostic_method=none``，以免把基础设施失败
    统计成被测模型能力错误。未知标签会被过滤，保留在输入中的原始诊断结果不写入报告。
    """
    scoring = scoring if isinstance(scoring, dict) else {}
    known = _known_errors()
    method = str(row.get("scoring_method") or "")
    verdict = str(scoring.get("verdict") or "")
    failure = (
        scoring.get("scoring_status") == "error"
        or scoring.get("judge_reason") in {"裁判输出无法解析", "未配置裁判模型"}
        or scoring.get("reason") in {"裁判解析失败", "未配置裁判模型"}
        or (method == "rubric_judge" and not scoring.get("judge_verdict") and not scoring.get("judge_scores") and not scoring.get("judge_raw"))
    )
    if failure:
        return {"error_tags": [], "error_evidence": [], "diagnostic_confidence": "low", "diagnostic_method": "none"}

    tags: list[str] = []
    evidence: list[str] = []
    for key in ("error_tags", "errors", "diagnostic_error_tags"):
        for tag in _as_tags(scoring.get(key), known):
            if tag not in tags:
                tags.append(tag)
    raw_evidence = scoring.get("error_evidence") or scoring.get("diagnostic_evidence") or []
    if isinstance(raw_evidence, str):
        raw_evidence = [raw_evidence]
    if isinstance(raw_evidence, (list, tuple)):
        evidence.extend(str(item) for item in raw_evidence if str(item).strip())

    # Rubric Judge 可以直接返回诊断字段；没有字段时至少使用题目声明的错误目标，
    # 但只对确实未通过的答案做推断，避免把通过题标成错误。
    if method == "rubric_judge":
        if verdict in {"REVIEW", "REJECT"} and not tags:
            for tag in _as_tags(row.get("error_targets"), known):
                if tag not in tags:
                    tags.append(tag)
        confidence = str(scoring.get("diagnostic_confidence") or ("medium" if tags else "low"))
        return {"error_tags": tags, "error_evidence": evidence, "diagnostic_confidence": confidence if confidence in {"low", "medium", "high"} else "medium", "diagnostic_method": "rubric_judge"}

    fmt = str(row.get("question_format") or "")
    if verdict in {"REVIEW", "REJECT"}:
        defaults = {
            "single_choice": ["similar_concept_confusion"],
            "multiple_choice": ["instruction_failure"],
            "true_false": ["rule_misapplication"],
            "numeric": ["amount_calculation_error"],
            "structured_extraction": ["factual_omission"],
            "compliance_response": ["refusal_failure"],
        }
        for tag in _as_tags(row.get("error_targets"), known) or defaults.get(fmt, []):
            if tag not in tags:
                tags.append(tag)
        if scoring.get("format_error"):
            tags.append("format_error")
        if not evidence and scoring.get("reason"):
            evidence.append(str(scoring["reason"]))
    return {
        "error_tags": list(dict.fromkeys(tags)),
        "error_evidence": list(dict.fromkeys(evidence)),
        "diagnostic_confidence": str(scoring.get("diagnostic_confidence") or ("medium" if tags else "low")),
        "diagnostic_method": "rule" if method in {"rule", "redline"} else "none",
    }


__all__ = ["diagnose_errors"]
