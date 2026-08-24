"""项目模块：tracks/legal_benchmark/validation/validate.py。

本文件属于三条评测线或公共工具层的一部分，负责完成本文件名对应的处理步骤。输入来自上游函数或数据目录，输出返回给下游函数或写入对应结果目录。

项目位置：tracks/legal_benchmark/validation/validate.py。
主要用途：法律真实案例 Benchmark，负责判决书解析、结构化提取、出题、校验和法律评测。
输入：输入来自法律线 data/raw、parsed、cleaned、drafts、releases 或 taxonomy/schema。
输出：输出按生命周期写入法律线对应 data 子目录或 results 目录。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：ingestion/extraction/generation/evaluation 可能写文件；只有带模型选项时才调用模型。
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from core import llm_client

from core.data_io import read_jsonl, write_jsonl
from core.json_utils import parse_json_object
from core.prompt_loader import load_template, render
from tracks.legal_benchmark.paths import DATA_ROOT, PROMPT_ROOT
from tracks.legal_benchmark.taxonomy import allowed_values, validate_cause_path

REQUIRED_FIELDS = (
    "question_id", "case_id", "split", "primary_issue", "task_type",
    "reasoning_capabilities", "answer_type", "scoring_method", "difficulty",
    "risk_level", "question", "reference_answer", "rubric", "source_evidence",
    "case_classification",
)
CONTROLLED_FIELDS = {
    "task_type": "task_types",
    "answer_type": "answer_types",
    "scoring_method": "scoring_methods",
    "difficulty": "difficulties",
    "risk_level": "risk_levels",
}


def check_row(row: dict, case: dict | None = None) -> list[str]:
    """校验一道法律题的字段、标签、来源引用和案件级 split。

    输入是正式题目以及可选的结构化案件；输出是问题字符串列表，空列表表示通过。
    校验不会修改题目，也不会调用模型。若传入案件，会额外确认每个 ``source_quote``
    出现在它声明的章节中，从而防止题目引用无法追溯的事实。
    """

    issues: list[str] = []
    for field in REQUIRED_FIELDS:
        if not row.get(field):
            issues.append(f"缺字段 {field}")

    for field, taxonomy_field in CONTROLLED_FIELDS.items():
        value = row.get(field)
        if value not in allowed_values(taxonomy_field):
            issues.append(f"{field} 非受控标签：{value}")
    for value in row.get("reasoning_capabilities", []):
        if value not in allowed_values("reasoning_capabilities"):
            issues.append(f"reasoning_capabilities 非受控标签：{value}")
    if row.get("split") not in {"dev", "calibration", "test"}:
        issues.append(f"split 非法：{row.get('split')}")
    classification = row.get("case_classification")
    if not isinstance(classification, dict):
        issues.append("case_classification 缺失或不是对象")
    else:
        primary = classification.get("primary_category", "")
        if classification.get("domain") not in allowed_values("domains"):
            issues.append(f"domain 非受控标签：{classification.get('domain')}")
        if classification.get("procedure_stage") not in allowed_values("procedure_stages"):
            issues.append(f"procedure_stage 非受控标签：{classification.get('procedure_stage')}")
        if classification.get("document_type") not in allowed_values("document_types"):
            issues.append(f"document_type 非受控标签：{classification.get('document_type')}")
        if primary not in allowed_values("primary_categories"):
            issues.append(f"primary_category 非受控标签：{primary}")
        if not validate_cause_path(primary, classification.get("cause_path", [])):
            issues.append(f"cause_path 非受控路径：{classification.get('cause_path')}")
        for value in classification.get("procedure_tags", []):
            if value not in allowed_values("procedure_tags"):
                issues.append(f"procedure_tags 非受控标签：{value}")
        for value in classification.get("evidence_tags", []):
            if value not in allowed_values("evidence_tags"):
                issues.append(f"evidence_tags 非受控标签：{value}")
    if case is not None:
        sections = case.get("sections", {})
        for evidence in row.get("source_evidence", []):
            section, quote = evidence.get("source_section", ""), evidence.get("source_quote", "")
            if section not in sections or not quote or quote not in sections.get(section, ""):
                issues.append(f"source_quote 无法在 {section} 定位")
    return issues


def validate(questions: list[dict], cases: list[dict] | None = None) -> list[dict]:
    """批量校验法律题集。输入是题目列表和可选案件列表，输出每题的 passed/failed 状态及问题说明。"""

    case_by_id: dict[str, dict] = {}
    for case in cases or []:
        case_by_id[case["case_id"]] = case
    split_by_case: dict[str, set[str]] = defaultdict(set)
    seen_questions: dict[str, str] = {}
    findings: list[dict] = []
    for row in questions:
        split_by_case[row.get("case_id", "")].add(row.get("split", ""))
        issues = check_row(row, case_by_id.get(row.get("case_id")) if cases is not None else None)
        text = row.get("question", "")
        if text in seen_questions:
            issues.append(f"与 {seen_questions[text]} 重复")
        elif text:
            seen_questions[text] = row.get("question_id", "")
        status = "pass" if not issues else "fail"
        findings.append({
            "question_id": row.get("question_id", ""),
            "case_id": row.get("case_id", ""),
            "status": status,
            "issues": issues,
        })
    for case_id, splits in split_by_case.items():
        if len(splits) > 1:
            findings.append({"question_id": "", "case_id": case_id, "status": "fail", "issues": [f"同案跨 split：{sorted(splits)}"]})
    return findings


def run(input_path: str | Path = DATA_ROOT / "releases" / "legal_questions.jsonl",
        cases_path: str | Path = DATA_ROOT / "cleaned" / "structured_cases.jsonl",
        output_path: str | Path = DATA_ROOT / "manifests" / "validation_report.jsonl",
        max_items: int | None = None, use_llm: bool = False) -> list[dict]:
    """完成当前模块中的一个处理步骤。

参数：input_path、cases_path、output_path、max_items、use_llm。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    questions = read_jsonl(input_path)
    if max_items is not None and max_items > 0:
        questions = questions[:max_items]
    cases = read_jsonl(cases_path) if Path(cases_path).is_file() else None
    findings = validate(questions, cases)
    if use_llm:
        llm_client.load_env()
        base, key, model = llm_client.read_role("VALIDATOR", "deepseek-v4-flash")
        client = llm_client.build_client(base, key)
        template = load_template("legal_validator_prompt.md", PROMPT_ROOT)
        by_id: dict[str, dict] = {}
        for item in findings:
            by_id[item["question_id"]] = item
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
    report = ["# 法律题集校验报告", "", f"- 题目数：{len(questions)}", f"- 失败项：{sum(item['status'] == 'fail' for item in findings)}", ""]
    for item in findings:
        report.append(f"- [{item['status'].upper()}] {item['question_id'] or item['case_id']}：{'；'.join(item['issues']) or '通过'}")
    Path(output_path).with_suffix(".md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return findings


def main() -> None:
    """完成当前模块中的一个处理步骤。

参数：无。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    parser = argparse.ArgumentParser(description="校验法律题集、受控标签、来源定位和案件级 split")
    parser.add_argument("--input", default=str(DATA_ROOT / "releases" / "legal_questions.jsonl"), help="正式题集 JSONL")
    parser.add_argument("--cases", default=str(DATA_ROOT / "cleaned" / "structured_cases.jsonl"), help="结构化案件 JSONL")
    parser.add_argument("--output", default=str(DATA_ROOT / "manifests" / "validation_report.jsonl"), help="校验结果 JSONL")
    parser.add_argument("--max-items", type=int, default=None, help="只校验前 N 题")
    parser.add_argument("--llm-check", action="store_true", help="增加模型语义复核")
    args = parser.parse_args()
    try:
        findings = run(args.input, args.cases, args.output, args.max_items, args.llm_check)
        failed = sum(item["status"] == "fail" for item in findings)
        print(f"完成：{args.output}，失败项 {failed}")
        raise SystemExit(1 if failed else 0)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

