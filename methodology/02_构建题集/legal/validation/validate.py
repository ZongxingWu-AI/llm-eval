"""法律题集发布前的结构、来源、隐私和可作答性校验。"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from core import llm_client
from core.data_io import read_jsonl, write_jsonl
from core.json_utils import parse_json_object
from core.prompt_loader import load_template, render
from core.project_paths import LEGAL_PROMPT_ROOT as PROMPT_ROOT
from core.run_metadata import new_run_metadata

from .answerability import validate_answerability
from .pii_scan import scan_pii
from .question_format_rules import validate_pairs, validate_question_format

_taxonomy = importlib.import_module("methodology.01_造Benchmark.legal.taxonomy")
_allowed_values = _taxonomy.allowed_values
_validate_cause_path = _taxonomy.validate_cause_path
_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "dimension_catalog.json"
_DEICTIC_RE = re.compile(r"(根据上述|如上所述|上文|前述|如前所述|见上文)")
_OUTCOME_MARKERS = ("判决如下", "裁判如下", "判决主文", "裁判主文", "本院判决", "裁定如下", "裁定主文", "判决：", "裁判：")


def _load_catalog() -> dict[str, Any]:
    """读取维度目录配置。"""
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"dimensions": []}


def _dimension_map() -> dict[str, dict[str, Any]]:
    """建立维度编号到维度配置的映射。"""
    return {
        str(item.get("dimension_id")): item
        for item in _load_catalog().get("dimensions", [])
        if isinstance(item, dict) and item.get("dimension_id")
    }


def _load_optional_catalog(name: str, fallback_field: str) -> set[str]:
    """读取专项标签或错误类型目录。"""
    try:
        config = importlib.import_module("methodology.02_构建题集.legal.config")
        loader = getattr(config, name)
        data = loader()
        if name == "load_error_taxonomy":
            return set((data.get("errors") or {}).keys())
        return set((data.get("tags") or {}).keys())
    except Exception:
        return _allowed_values(fallback_field)


def _context_text(value: Any) -> str:
    """将上下文转换为可检查的文本。"""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, default=str)


def _is_prediction(row: dict[str, Any]) -> bool:
    """判断题目是否为裁判结果预测题。"""
    return row.get("dimension_id") == "judgment_prediction" or row.get("task_type") == "裁判结果预测"


def build_model_input(row: dict[str, Any]) -> str:
    """构造只包含 context、question、options 的模拟作答输入。"""
    context = _context_text(row.get("context")).strip()
    question = str(row.get("question") or "").strip()
    text = f"案件材料：\n{context}\n\n问题：\n{question}" if context else question
    if row.get("question_format") in {"single_choice", "multiple_choice"}:
        options = row.get("options") or []
        lines = [f"{item.get('option_id')}. {item.get('text')}" for item in options if isinstance(item, dict)]
        if lines:
            text += "\n\n选项：\n" + "\n".join(lines)
    return text


def _all_case_text(case: dict[str, Any] | None) -> str:
    """返回案件唯一的脱敏全文，供来源引用校验。"""
    case = case or {}
    value = case.get("external_text")
    return str(value) if isinstance(value, str) else ""


def _outcome_start(text: str) -> int:
    """返回文本中最早出现的明确裁判结果标记位置。"""
    positions = [text.find(marker) for marker in _OUTCOME_MARKERS if text.find(marker) >= 0]
    return min(positions) if positions else -1


def _source_evidence_issues(row: dict[str, Any], case: dict[str, Any] | None) -> list[str]:
    """检查来源引用是否逐字存在且哈希一致。"""
    issues: list[str] = []
    evidence_items = row.get("source_evidence")
    if not isinstance(evidence_items, list) or not evidence_items:
        return ["source_evidence 至少需要一条来源引用"]
    all_text = _all_case_text(case)
    for evidence in evidence_items:
        if not isinstance(evidence, dict):
            issues.append("source_evidence 项不是对象")
            continue
        extra_fields = set(evidence) - {"source_quote", "source_quote_sha256"}
        if extra_fields:
            issues.append("source_evidence 包含未定义字段")
        quote = str(evidence.get("source_quote") or "").strip()
        if not quote:
            issues.append("source_evidence 缺少 source_quote")
            continue
        digest = str(evidence.get("source_quote_sha256") or "").lower()
        if digest and digest != hashlib.sha256(quote.encode("utf-8")).hexdigest():
            issues.append("source_quote_sha256 与 source_quote 不一致")
        if case and quote not in all_text:
            issues.append("source_quote 无法在案件脱敏全文中逐字定位")
        if _is_prediction(row) and all_text:
            start = all_text.find(quote)
            outcome = _outcome_start(all_text)
            if start >= 0 and outcome >= 0 and start >= outcome:
                issues.append("预测题 source_quote 位于明确裁判结果区域")
    return issues

def _answer_leak_issues(row: dict[str, Any]) -> list[str]:
    """检查题面、背景和预测题是否泄露参考答案或裁判结论。"""
    context = _context_text(row.get("context"))
    question = str(row.get("question") or "")
    answer = str(row.get("reference_answer") or "").strip()
    issues: list[str] = []
    if answer and len(answer) >= 8 and answer in question:
        issues.append("question 直接泄露 reference_answer")
    if answer and len(answer) >= 12 and answer in context:
        issues.append("context 直接包含完整 reference_answer，需检查是否答案泄露")
    if _is_prediction(row):
        if row.get("judgment_results"):
            issues.append("裁判结果预测题不应携带 judgment_results")
        if any(marker in context for marker in (*_OUTCOME_MARKERS, "支持原告", "驳回原告")):
            issues.append("预测题 context 泄露法院结论")
    return issues


def _legacy_format(row: dict[str, Any]) -> str | None:
    """为旧题按评分方式推断兼容题型。"""
    fmt = str(row.get("question_format") or "").strip()
    if fmt:
        return fmt
    return {"rule": None, "redline": "compliance_response", "rubric_judge": "case_analysis"}.get(row.get("scoring_method"))


def check_row(row: dict[str, Any], case: dict[str, Any] | None = None) -> list[str]:
    """校验单题，返回可读错误列表；旧题允许缺少新增字段并按旧评分方式检查。"""
    if not isinstance(row, dict):
        return ["题目记录必须是对象"]
    issues: list[str] = []
    required = ("question_id", "case_id", "split", "dimension_id", "task_type", "question", "reference_answer", "rubric", "source_evidence")
    for field in required:
        if row.get(field) in (None, ""):
            issues.append(f"缺少字段：{field}")
    for field, values_key in {
        "split": "splits", "task_type": "task_types", "dimension_id": "dimension_ids", "scoring_method": "scoring_methods", "difficulty": "difficulties", "risk_level": "risk_levels", "context_type": "context_types",
    }.items():
        value = row.get(field)
        allowed = _allowed_values(values_key)
        if value is not None and allowed and str(value) not in allowed:
            issues.append(f"{field} 不在受控词表中：{value}")
    dimensions = _dimension_map()
    dimension_id = str(row.get("dimension_id") or "")
    dimension = dimensions.get(dimension_id)
    if dimension:
        if row.get("task_type") and row.get("task_type") != dimension.get("task_type"):
            issues.append(f"task_type 与 dimension_id 不匹配：{dimension_id}")
        if row.get("context_type") and row.get("context_type") not in (dimension.get("context_types") or []):
            issues.append(f"context_type 不适用于维度：{dimension_id}")
        if row.get("scoring_method") and row.get("scoring_method") != dimension.get("scoring_method"):
            issues.append(f"scoring_method 与维度配置不匹配：{dimension_id}")
        classification = row.get("case_classification")
        category = classification.get("primary_category") if isinstance(classification, dict) else None
        if category and dimension.get("applicable_case_types") and category not in dimension["applicable_case_types"]:
            issues.append(f"案件类别不适用于维度：{category} -> {dimension_id}")
    elif dimension_id:
        issues.append(f"无效 dimension_id：{dimension_id}")
    tags = row.get("sample_tags")
    if tags is not None:
        if not isinstance(tags, list):
            issues.append("sample_tags 必须是数组")
        else:
            known = _load_optional_catalog("load_sample_tag_catalog", "sample_tags")
            issues.extend(f"sample_tags 包含未知标签：{tag}" for tag in tags if str(tag) not in known)
    targets = row.get("error_targets")
    if targets is not None:
        if not isinstance(targets, list):
            issues.append("error_targets 必须是数组")
        else:
            known = _load_optional_catalog("load_error_taxonomy", "error_types")
            issues.extend(f"error_targets 包含未知错误类型：{tag}" for tag in targets if str(tag) not in known)
    classification = row.get("case_classification") or {}
    if isinstance(classification, dict) and classification.get("primary_category") and classification.get("cause_path"):
        if not _validate_cause_path(str(classification["primary_category"]), classification["cause_path"]):
            issues.append("case_classification.cause_path 不在受控案由树中")
    context = _context_text(row.get("context")).strip()
    question = str(row.get("question") or "").strip()
    if not context:
        issues.append("context 为空，题目不可独立作答")
    if context == question and context:
        issues.append("context 不能仅重复 question；必须提供独立案件材料")
    if _DEICTIC_RE.search(question):
        issues.append("question 依赖未保存的上文")
    issues.extend(validate_answerability(row))
    if row.get("question_format"):
        issues.extend(validate_question_format(row))
    elif _legacy_format(row) == "compliance_response":
        issues.append("新题必须明确 question_format")
    issues.extend(_source_evidence_issues(row, case))
    issues.extend(_answer_leak_issues(row))
    if scan_pii(row.get("context")):
        issues.append("context 包含未脱敏 PII")
    if scan_pii(row.get("source_evidence")):
        issues.append("source_evidence 包含未脱敏 PII")
    return list(dict.fromkeys(issues))


def validate(questions: list[dict[str, Any]], cases: list[dict[str, Any]] | None = None, blueprint: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """批量校验题目，并检查 question_id、案件级 split、成对题和蓝图配额。"""
    case_map = {str(item.get("case_id")): item for item in (cases or []) if isinstance(item, dict)}
    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    split_map: dict[str, set[str]] = defaultdict(set)
    for row in questions:
        qid = str(row.get("question_id") or "")
        issues = check_row(row, case_map.get(str(row.get("case_id"))))
        if qid in seen:
            issues.append("question_id 重复")
        seen.add(qid)
        split_map[str(row.get("case_id") or "")].add(str(row.get("split") or ""))
        findings.append({"question_id": qid, "case_id": row.get("case_id", ""), "dimension_id": row.get("dimension_id", ""), "status": "fail" if issues else "pass", "issues": list(dict.fromkeys(issues))})
    for case_id, splits in split_map.items():
        if case_id and len(splits) > 1:
            for finding in findings:
                if finding["case_id"] == case_id:
                    finding["status"] = "fail"
                    finding["issues"] = list(dict.fromkeys(finding["issues"] + ["同案跨 split"]))
    for pair_issue in validate_pairs(questions):
        findings.append({"question_id": "", "case_id": "", "dimension_id": "", "status": "fail", "issues": [pair_issue]})
    if blueprint:
        targets = blueprint.get("dimension_quotas", blueprint.get("dimension_targets", {})) or {}
        counts: dict[str, int] = defaultdict(int)
        for row in questions:
            counts[str(row.get("dimension_id") or "")] += 1
        for dimension_id, target in targets.items():
            if counts[str(dimension_id)] < int(target):
                findings.append({"question_id": "", "case_id": "", "dimension_id": str(dimension_id), "status": "warning", "issues": [f"维度配额不足：目标 {target}，实际 {counts[str(dimension_id)]}"]})
    return findings


def run(
    input_path: str | Path, cases_path: str | Path, output_path: str | Path,
    max_items: int | None = None, use_llm: bool = False,
    blueprint_path: str | Path | None = None,
    generator_base_url: str | None = None, generator_model: str | None = None,
) -> list[dict[str, Any]]:
    """运行规则校验和可选的独立 Reviewer 复核。"""
    questions = read_jsonl(input_path)
    if max_items and max_items > 0:
        questions = questions[:max_items]
    cases = read_jsonl(cases_path) if Path(cases_path).is_file() else []
    blueprint = json.loads(Path(blueprint_path).read_text(encoding="utf-8")) if blueprint_path and Path(blueprint_path).is_file() else None
    findings = validate(questions, cases, blueprint)
    reviewer_model = ""
    reviewer_base_url = ""
    generator_identity = (generator_base_url or "", generator_model or "")
    reviewer_is_independent = False
    if use_llm:
        llm_client.load_env()
        if not generator_base_url or not generator_model:
            gen_base, _gen_key, gen_model = llm_client.read_role("GENERATOR", "deepseek-v4-flash")
            generator_identity = (generator_base_url or gen_base, generator_model or gen_model)
        reviewer_base_url, reviewer_key, reviewer_model = llm_client.read_explicit_role("REVIEWER")
        llm_client.ensure_roles_distinct(generator_identity, (reviewer_base_url, reviewer_model))
        reviewer_is_independent = True
        client = llm_client.build_client(reviewer_base_url, reviewer_key)
        template = load_template("legal_validator_prompt.md", PROMPT_ROOT)
        by_id = {str(item.get("question_id")): item for item in findings if item.get("question_id")}
        for row in questions:
            finding = by_id.get(str(row.get("question_id")))
            if not finding:
                continue
            try:
                review_input = {
                    key: row.get(key) for key in (
                        "dimension_id", "question_format", "context", "question",
                        "options", "reference_answer", "rubric", "source_evidence",
                    ) if key in row
                }
                prompt = render(template, {"item": json.dumps(review_input, ensure_ascii=False)})
                raw = llm_client.call_model(client, reviewer_model, prompt, 0, 8192)[0]
                result = parse_json_object(raw)
                if result.get("pass") is False:
                    finding["status"] = "fail"
                    finding["issues"].extend(str(item) for item in result.get("issues", []) if str(item).strip())
            except Exception as exc:
                finding["status"] = "fail"
                finding["issues"].append("Reviewer 复核输出无法解析：" + str(exc))
    output = Path(output_path)
    write_jsonl(output, findings)
    report = output.with_suffix(".md")
    report.write_text("# 法律题集校验报告\n\n" + "\n".join(f"- [{item['status'].upper()}] {item.get('question_id') or item.get('dimension_id')}: {'；'.join(item.get('issues', [])) or '通过'}" for item in findings) + "\n", encoding="utf-8")
    failures = sum(1 for item in findings if item["status"] == "fail")
    metadata = new_run_metadata(
        "legal_benchmark.validation", input=str(input_path), cases=str(cases_path),
        output=str(output), report=str(report), questions=len(questions), failures=failures,
        method="rules+reviewer" if use_llm else "rules", model=reviewer_model,
    )
    metadata.update({
        "generator_model": generator_identity[1],
        "generator_base_url": generator_identity[0],
        "reviewer_model": reviewer_model,
        "reviewer_base_url": reviewer_base_url,
        "reviewer_is_independent": reviewer_is_independent,
    })
    output.with_suffix(output.suffix + ".metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return findings


def main() -> None:
    """解析题集校验命令行参数并执行校验。"""
    parser = argparse.ArgumentParser(description="校验法律题集、题型契约、来源定位、隐私和案件级 split")
    parser.add_argument("--input", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--blueprint")
    parser.add_argument("--max-items", type=int)
    parser.add_argument("--llm-check", action="store_true")
    args = parser.parse_args()
    try:
        findings = run(args.input, args.cases, args.output, args.max_items, args.llm_check, args.blueprint)
        print(f"完成：{args.output}，失败项 {sum(item['status'] == 'fail' for item in findings)}")
        raise SystemExit(1 if any(item["status"] == "fail" for item in findings) else 0)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
