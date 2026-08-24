"""法律正式题集验证模块。

项目位置：法律真实案例评测线的 validation 阶段。
输入：releases/legal_questions.jsonl，以及可选的 cleaned 结构化案件。
输出：validation_report.jsonl 和 Markdown 摘要，逐题记录 valid 与 issues。
上下游：上游是 dataset.build，下游是冻结题集后的 evaluation.run。
副作用：覆盖验证报告；默认只做规则校验，传入 --use-llm 时才调用裁判模型。"""

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
    """用途：校验一道正式法律题的必填字段、受控标签、split 和来源引用。

    输入：row 是正式题目；case 可选，是同 case_id 的结构化案件。
    输出：返回问题字符串列表，空列表表示该题通过规则校验。
    运行前数据形态：运行前题目可能缺字段或含无来源证据。
    运行后数据变化：运行后题目本身不变，只生成可人工处理的问题列表。
    副作用：读取 taxonomy；只处理内存，不写文件、不调用模型。
    异常或失败处理：每个问题单独追加，允许一次看到全部缺陷；case 存在时 source_quote 无法定位会报错。
    最小示例：source_section=judgment 但 quote 不在主文时返回定位错误。"""

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
    """用途：批量校验正式题集，并额外检查同一案件是否跨 split。

    输入：questions 是正式题目列表；cases 可选，用于引用定位。
    输出：返回每题一条验证记录，包含 question_id、case_id、valid 和 issues。
    运行前数据形态：运行前是一组待验证问题和可选案件。
    运行后数据变化：运行后得到逐题验证报告，不修改原题。
    副作用：只处理内存并读取 taxonomy，不写文件、不调用模型。
    异常或失败处理：找不到案件时仍执行字段校验；同案出现多个 split 时为相关题追加错误。"""

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
    """用途：读取正式题集和可选案件，执行规则验证，并可用模型对通过项做补充复核。

    输入：input_path、cases_path、output_path、max_items、use_llm 控制验证范围和方式。
    输出：返回验证记录列表；写 validation_report.jsonl 和同目录 Markdown 摘要。
    运行前数据形态：运行前是一行一道正式题。
    运行后数据变化：运行后每行标记 valid 与问题列表，报告汇总通过和失败数量。
    副作用：读取 JSONL、创建目录并覆盖报告；仅 use_llm=True 时读取 JUDGE 配置并调用模型。
    异常或失败处理：模型复核失败会记录到该题 issues；文件或配置错误按调用方异常策略处理。"""

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
    failure_count = 0
    for item in findings:
        if item["status"] == "fail":
            failure_count += 1
    report = [
        "# 法律题集校验报告",
        "",
        f"- 题目数：{len(questions)}",
        f"- 失败项：{failure_count}",
        "",
    ]
    for item in findings:
        report.append(f"- [{item['status'].upper()}] {item['question_id'] or item['case_id']}：{'；'.join(item['issues']) or '通过'}")
    Path(output_path).with_suffix(".md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return findings


def main() -> None:
    """用途：提供题集验证 CLI，并用退出码区分全部通过和存在失败项。

    输入：参数来自 argparse；默认验证 releases/legal_questions.jsonl，可选 cleaned 案件和 --use-llm。
    输出：写出 JSONL/Markdown 报告；全部有效时退出 0，有任一无效题时退出 1。
    运行前数据形态：运行前是正式题集和命令行参数。
    运行后数据变化：运行后生成发布前质量报告，阻止无来源或跨 split 题进入评测。
    副作用：创建目录并覆盖验证报告；只有 --use-llm 时调用裁判模型。
    异常或失败处理：参数错误由 argparse 处理；运行异常或验证失败均产生非零退出。"""

    parser = argparse.ArgumentParser(description="校验法律题集、受控标签、来源定位和案件级 split")
    parser.add_argument("--input", default=str(DATA_ROOT / "releases" / "legal_questions.jsonl"), help="正式题集 JSONL")
    parser.add_argument("--cases", default=str(DATA_ROOT / "cleaned" / "structured_cases.jsonl"), help="结构化案件 JSONL")
    parser.add_argument("--output", default=str(DATA_ROOT / "manifests" / "validation_report.jsonl"), help="校验结果 JSONL")
    parser.add_argument("--max-items", type=int, default=None, help="只校验前 N 题")
    parser.add_argument("--llm-check", action="store_true", help="增加模型语义复核")
    args = parser.parse_args()
    try:
        findings = run(args.input, args.cases, args.output, args.max_items, args.llm_check)
        failed = 0
        for item in findings:
            if item["status"] == "fail":
                failed += 1
        print(f"完成：{args.output}，失败项 {failed}")
        raise SystemExit(1 if failed else 0)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

