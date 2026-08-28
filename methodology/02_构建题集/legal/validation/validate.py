"""法律题集质量校验。

除旧有 taxonomy、来源引用和案件级 split 校验外，本模块还校验维度驱动题集契约：
dimension_id、task_type、context_type、context 的一致性，以及题面答案泄露和可作答性。
校验只读输入，不调用被测模型；--llm-check 仍可由调用方选择额外的语义复核。
"""

from __future__ import annotations

import argparse
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

_taxonomy = importlib.import_module("methodology.01_造Benchmark.legal.taxonomy")
allowed_values = _taxonomy.allowed_values
validate_cause_path = _taxonomy.validate_cause_path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "dimension_catalog.json"
REQUIRED_FIELDS = (
    "question_id", "case_id", "split", "case_classification", "dimension_id", "context_type", "context",
    "primary_issue", "task_type", "reasoning_capabilities", "answer_type", "scoring_method",
    "difficulty", "risk_level", "question", "reference_answer", "rubric", "source_evidence",
)
CONTROLLED_FIELDS = {
    "task_type": "task_types", "answer_type": "answer_types", "scoring_method": "scoring_methods",
    "difficulty": "difficulties", "risk_level": "risk_levels",
}
CONTEXT_TYPES = {"self_contained", "source_excerpt", "full_document", "scenario"}
DEICTIC_RE = re.compile(r"(根据上述|如上所述|上文|前述|如前所述)")


def _load_catalog() -> dict[str, Any]:
    """执行法律题集流程辅助操作。"""
    if not CONFIG_PATH.is_file():
        return {"dimensions": []}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _dimension_map() -> dict[str, dict[str, Any]]:
    """执行法律题集流程辅助操作。"""
    return {
        str(item.get("dimension_id")): item
        for item in _load_catalog().get("dimensions", [])
        if isinstance(item, dict) and item.get("dimension_id")
    }


def _allowed_context(config: dict[str, Any]) -> set[str]:
    """执行法律题集流程辅助操作。"""
    values = config.get("allowed_context_types", config.get("context_types", []))
    if isinstance(values, str):
        values = [values]
    if not values and config.get("context_type"):
        values = [config["context_type"]]
    if not values and config.get("default_context_type"):
        values = [config["default_context_type"]]
    return {str(value) for value in values}


def _context_text(context: Any) -> str:
    """执行法律题集流程辅助操作。"""
    if isinstance(context, str):
        return context
    if context is None:
        return ""
    return json.dumps(context, ensure_ascii=False)


def _is_judgment_prediction(row: dict[str, Any]) -> bool:
    """执行法律题集流程辅助操作。"""
    return str(row.get("dimension_id", "")) == "judgment_prediction" or row.get("task_type") == "裁判结果预测"


def _answer_leak_issues(row: dict[str, Any]) -> list[str]:
    """执行法律题集流程辅助操作。"""
    question = str(row.get("question", ""))
    context = _context_text(row.get("context"))
    reference = str(row.get("reference_answer", ""))
    issues: list[str] = []
    if reference.strip() and len(reference.strip()) >= 8 and reference.strip() in question + "\n" + context:
        issues.append("题面或 context 直接包含完整参考答案")
    if _is_judgment_prediction(row):
        forbidden = ("判决如下", "裁判结果", "法院判令", "本院认为", "驳回诉讼请求", "支持原告")
        if any(marker in context for marker in forbidden):
            issues.append("裁判结果预测题的 context 疑似泄露法院结论")
    return issues


def build_model_input(row: dict[str, Any]) -> str:
    """模拟 03 发送给被测模型的输入，确保题目不依赖隐藏的上文。"""
    context = _context_text(row.get("context"))
    question = str(row.get("question", ""))
    if not context:
        return question
    return f"案件材料：\n{context}\n\n问题：\n{question}"


def check_row(row: dict[str, Any], case: dict[str, Any] | None = None) -> list[str]:
    """执行法律题集流程辅助操作。"""
    issues: list[str] = []
    for field in REQUIRED_FIELDS:
        if row.get(field) is None or row.get(field) == "" or row.get(field) == []:
            issues.append(f"缺字段 {field}")

    for field, taxonomy_field in CONTROLLED_FIELDS.items():
        if row.get(field) not in allowed_values(taxonomy_field):
            issues.append(f"{field} 非受控标签：{row.get(field)}")
    capabilities = row.get("reasoning_capabilities", [])
    if not isinstance(capabilities, list) or not capabilities:
        issues.append("reasoning_capabilities 必须是非空数组")
    else:
        for value in capabilities:
            if value not in allowed_values("reasoning_capabilities"):
                issues.append(f"reasoning_capabilities 非受控标签：{value}")
        if len(capabilities) > 3:
            issues.append("一题包含过多互不相关的 reasoning_capabilities")

    dimension = _dimension_map().get(str(row.get("dimension_id", "")))
    if not dimension:
        issues.append(f"dimension_id 非受控维度：{row.get('dimension_id')}")
    else:
        expected_task = dimension.get("task_type")
        if expected_task and row.get("task_type") != expected_task:
            issues.append(f"task_type 与 dimension_id 不匹配：应为 {expected_task}")
        contexts = _allowed_context(dimension)
        if row.get("context_type") not in CONTEXT_TYPES:
            issues.append(f"context_type 非法：{row.get('context_type')}")
        elif contexts and row.get("context_type") not in contexts:
            issues.append(f"context_type 不适用于该维度：{row.get('context_type')}")
        recommended = dimension.get("scoring_methods", dimension.get("scoring_method"))
        if isinstance(recommended, str):
            recommended = [recommended]
        if recommended and row.get("scoring_method") not in recommended:
            issues.append(f"scoring_method 不适用于该维度：{row.get('scoring_method')}")

    context = _context_text(row.get("context"))
    question = str(row.get("question", ""))
    if not context:
        issues.append("context 不能为空：新题必须显式提供可作答材料")
    elif context.strip() == question.strip():
        issues.append("context 不能仅重复 question：新题必须提供独立案件材料")
    if DEICTIC_RE.search(question) and not context:
        issues.append("question 依赖未提供的上文材料")
    if _is_judgment_prediction(row) and row.get("context_type") == "full_document":
        issues.append("裁判结果预测题不能直接传入包含裁判结果的完整文书")
    issues.extend(_answer_leak_issues(row))

    classification = row.get("case_classification")
    if not isinstance(classification, dict):
        issues.append("case_classification 缺失或不是对象")
    else:
        primary = classification.get("primary_category", "")
        for case_field, taxonomy_field in (
            ("domain", "domains"), ("procedure_stage", "procedure_stages"),
            ("document_type", "document_types"), ("primary_category", "primary_categories"),
        ):
            if classification.get(case_field) not in allowed_values(taxonomy_field):
                issues.append(f"{case_field} 非受控标签：{classification.get(case_field)}")
        if not validate_cause_path(primary, classification.get("cause_path", [])):
            issues.append(f"cause_path 非受控路径：{classification.get('cause_path')}")
        for value in classification.get("procedure_tags", []):
            if value not in allowed_values("procedure_tags"):
                issues.append(f"procedure_tags 非受控标签：{value}")
        for value in classification.get("evidence_tags", []):
            if value not in allowed_values("evidence_tags"):
                issues.append(f"evidence_tags 非受控标签：{value}")

    evidence = row.get("source_evidence", [])
    if not isinstance(evidence, list) or not evidence:
        issues.append("source_evidence 必须是非空数组")
    for item in evidence if isinstance(evidence, list) else []:
        if not isinstance(item, dict) or not item.get("source_section") or not item.get("source_quote"):
            issues.append("source_evidence 条目缺少 source_section/source_quote")

    if case is not None:
        sections = case.get("sections", {})
        full_text = str(case.get("full_text", ""))
        for item in evidence if isinstance(evidence, list) else []:
            if not isinstance(item, dict):
                continue
            section, quote = item.get("source_section", ""), item.get("source_quote", "")
            section_text = sections.get(section, "") if isinstance(sections, dict) else ""
            if not quote or (quote not in str(section_text) and quote not in full_text):
                issues.append(f"source_quote 无法在 {section} 定位")
    return issues


def validate(questions: list[dict[str, Any]], cases: list[dict[str, Any]] | None = None,
             blueprint: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """执行法律题集流程辅助操作。"""
    case_by_id = {str(case["case_id"]): case for case in cases or [] if case.get("case_id")}
    split_by_case: dict[str, set[str]] = defaultdict(set)
    seen_questions: dict[str, str] = {}
    findings: list[dict[str, Any]] = []
    for row in questions:
        question_id = str(row.get("question_id", ""))
        split_by_case[str(row.get("case_id", ""))].add(str(row.get("split", "")))
        issues = check_row(row, case_by_id.get(str(row.get("case_id"))))
        text = str(row.get("question", ""))
        if text in seen_questions and text:
            issues.append(f"与 {seen_questions[text]} 重复")
        elif text:
            seen_questions[text] = question_id
        findings.append({"question_id": question_id, "case_id": row.get("case_id", ""),
                         "dimension_id": row.get("dimension_id", ""), "status": "pass" if not issues else "fail",
                         "issues": issues})
    for case_id, splits in split_by_case.items():
        if len(splits) > 1:
            findings.append({"question_id": "", "case_id": case_id, "status": "fail",
                             "issues": [f"同案跨 split：{sorted(splits)}"]})

    if blueprint:
        quotas = blueprint.get("dimension_quotas", blueprint.get("quotas", {}))
        counts = defaultdict(int)
        for row in questions:
            counts[str(row.get("dimension_id", ""))] += 1
        for dimension_id, target in quotas.items() if isinstance(quotas, dict) else []:
            try:
                shortage = int(target) - counts[str(dimension_id)]
            except (TypeError, ValueError):
                continue
            if shortage > 0:
                findings.append({"question_id": "", "case_id": "", "dimension_id": dimension_id,
                                 "status": "warning", "issues": [f"维度配额不足：目标 {target}，实际 {counts[str(dimension_id)]}"]})
    return findings


def run(input_path: str | Path, cases_path: str | Path, output_path: str | Path,
        max_items: int | None = None, use_llm: bool = False,
        blueprint_path: str | Path | None = None) -> list[dict[str, Any]]:
    """执行法律题集流程辅助操作。"""
    model = ""
    questions = read_jsonl(input_path)
    if max_items is not None and max_items > 0:
        questions = questions[:max_items]
    cases = read_jsonl(cases_path) if Path(cases_path).is_file() else None
    blueprint = None
    if blueprint_path and Path(blueprint_path).is_file():
        blueprint = json.loads(Path(blueprint_path).read_text(encoding="utf-8"))
    findings = validate(questions, cases, blueprint)
    if use_llm:
        llm_client.load_env()
        base, key, model = llm_client.read_role("VALIDATOR", "deepseek-v4-flash")
        client = llm_client.build_client(base, key)
        template = load_template("legal_validator_prompt.md", PROMPT_ROOT)
        by_id = {item["question_id"]: item for item in findings if item.get("question_id")}
        for question in questions:
            prompt = render(template, {"item": json.dumps(question, ensure_ascii=False)})
            raw = llm_client.call_model(client, model, prompt, 0, 8192)[0]
            try:
                result = parse_json_object(raw)
                if result.get("pass") is False:
                    by_id[question["question_id"]]["issues"].extend(result.get("issues", []))
                    by_id[question["question_id"]]["status"] = "fail"
            except ValueError:
                by_id[question["question_id"]]["issues"].append("模型复核输出无法解析")
                by_id[question["question_id"]]["status"] = "fail"
    write_jsonl(output_path, findings)
    failures = sum(1 for item in findings if item["status"] == "fail")
    report_path = Path(output_path).with_suffix(".md")
    report = ["# 法律题集校验报告", "", f"- 题目数：{len(questions)}", f"- 失败项：{failures}", ""]
    for item in findings:
        report.append(f"- [{item['status'].upper()}] {item.get('question_id') or item.get('case_id') or item.get('dimension_id')}: {'；'.join(item.get('issues', [])) or '通过'}")
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    metadata = new_run_metadata("legal_benchmark.validation", input=str(input_path), cases=str(cases_path),
                                output=str(output_path), report=str(report_path), questions=len(questions),
                                failures=failures, method="rules+llm" if use_llm else "rules", model=model)
    Path(output_path).with_suffix(Path(output_path).suffix + ".metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return findings


def main() -> None:
    """执行法律题集流程辅助操作。"""
    parser = argparse.ArgumentParser(description="校验法律题集、维度契约、上下文策略、来源定位和案件级 split")
    parser.add_argument("--input", required=True, help="正式题集 JSONL")
    parser.add_argument("--cases", required=True, help="extract 阶段案件 JSONL")
    parser.add_argument("--output", required=True, help="校验结果 JSONL")
    parser.add_argument("--blueprint", default=None, help="可选题集蓝图 JSON")
    parser.add_argument("--max-items", type=int, default=None, help="只校验前 N 题")
    parser.add_argument("--llm-check", action="store_true", help="增加模型语义复核")
    args = parser.parse_args()
    try:
        findings = run(args.input, args.cases, args.output, args.max_items, args.llm_check, args.blueprint)
        failed = sum(1 for item in findings if item["status"] == "fail")
        print(f"完成：{args.output}，失败项 {failed}")
        raise SystemExit(1 if failed else 0)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
