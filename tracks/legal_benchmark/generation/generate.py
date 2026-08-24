"""项目模块：tracks/legal_benchmark/generation/generate.py。

本文件属于三条评测线或公共工具层的一部分，负责完成本文件名对应的处理步骤。输入来自上游函数或数据目录，输出返回给下游函数或写入对应结果目录。

项目位置：tracks/legal_benchmark/generation/generate.py。
主要用途：法律真实案例 Benchmark，负责判决书解析、结构化提取、出题、校验和法律评测。
输入：输入来自法律线 data/raw、parsed、cleaned、drafts、releases 或 taxonomy/schema。
输出：输出按生命周期写入法律线对应 data 子目录或 results 目录。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：ingestion/extraction/generation/evaluation 可能写文件；只有带模型选项时才调用模型。
"""

import argparse
import json
import sys
from pathlib import Path

from core.json_utils import parse_json_value
from core.prompt_loader import load_template, render
from core.run_metadata import new_run_metadata
from tracks.legal_benchmark.paths import DATA_ROOT, PROMPT_ROOT
from tracks.legal_benchmark.taxonomy import load_taxonomy

REQUIRED_FIELDS = ("primary_issue", "task_type", "reasoning_capabilities", "answer_type", "scoring_method",
                   "difficulty", "risk_level", "question", "reference_answer", "rubric", "source_evidence")


def _valid_evidence(case: dict, evidence) -> list[dict]:
    """筛选能够回溯到案件章节的题目证据。

    输入是结构化案件和模型生成的证据列表；输出只保留章节名存在、
    且引用文字确实出现在该章节中的字典。函数不调用模型、不写文件，
    空或非法证据会返回空列表，令上游拒绝无法追溯的候选题。
    """

    sections = case.get("sections", {})
    valid: list[dict] = []
    if not isinstance(evidence, list):
        return valid
    for item in evidence:
        if not isinstance(item, dict):
            continue
        section = item.get("source_section")
        quote = item.get("source_quote")
        section_text = sections.get(section, "")
        if section not in sections or not quote or quote not in section_text:
            continue
        valid.append({"source_section": section, "source_quote": quote})
    return valid


def generate_one_case(case: dict, client, model: str, questions_per_case: int) -> tuple[list[dict], list[str]]:
    """调用生成模型，为一个案件生成候选题和错误记录。

    调用前输入是 cleaned 阶段案件；调用后每个候选题会补上 ``case_id``、
    ``case_classification`` 和 ``review_status=pending``。只有必填字段齐全且
    ``source_evidence`` 能回溯到原案件章节的题目才进入结果列表；模型输出解析失败
    或证据定位失败会进入错误列表，不会静默写入正式题集。
    """

    template = load_template("legal_generation_prompt.md", PROMPT_ROOT)
    prompt = render(template, {"case": json.dumps(case, ensure_ascii=False),
                               "taxonomy": json.dumps(load_taxonomy(), ensure_ascii=False),
                               "questions_per_case": questions_per_case})
    raw = llm_client.call_model(client, model, prompt, 0, 8192)[0]
    value = parse_json_value(raw)
    items = value if isinstance(value, list) else [value]
    results: list[dict] = []
    errors: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"第 {index + 1} 项不是对象")
            continue
        missing = []
        for field in REQUIRED_FIELDS:
            if not item.get(field):
                missing.append(field)
        evidence = _valid_evidence(case, item.get("source_evidence"))
        if missing or not evidence:
            errors.append(f"第 {index + 1} 项缺字段或来源定位无效：{missing}")
            continue
        item["case_id"] = case["case_id"]
        item["source_evidence"] = evidence
        item["review_status"] = "pending"
        item["case_classification"] = case.get("classification", {})
        results.append(item)
    return results, errors


def run(input_path: str | Path = DATA_ROOT / "cleaned" / "structured_cases.jsonl",
        output_path: str | Path = DATA_ROOT / "drafts" / "candidate_questions.jsonl",
        max_items: int | None = None, case_ids: set[str] | None = None, questions_per_case: int = 2) -> list[dict]:
    """完成当前模块中的一个处理步骤。

参数：input_path、output_path、max_items、case_ids、questions_per_case。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    cases = read_jsonl(input_path)
    if case_ids:
        cases = [case for case in cases if case.get("case_id") in case_ids]
    if max_items is not None and max_items > 0:
        cases = cases[:max_items]
    llm_client.load_env()
    base, key, model = llm_client.read_role("GENERATOR", "deepseek-v4-flash")
    client = llm_client.build_client(base, key)
    drafts: list[dict] = []
    errors: list[dict] = []
    for index, case in enumerate(cases, start=1):
        print(f"[出题] {index}/{len(cases)} {case.get('case_id', '')}")
        try:
            generated, case_errors = generate_one_case(case, client, model, questions_per_case)
            drafts.extend(generated)
            errors.extend({"case_id": case.get("case_id"), "error": error} for error in case_errors)
        except Exception as exc:
            errors.append({"case_id": case.get("case_id"), "error": str(exc)})
    write_jsonl(output_path, drafts)
    error_path = Path(output_path).with_suffix(".errors.jsonl")
    write_jsonl(error_path, errors)
    metadata = new_run_metadata("legal_benchmark.generation", input=str(input_path), output=str(output_path),
                                cases=len(cases), questions=len(drafts), errors=len(errors), model=model)
    Path(output_path).with_suffix(Path(output_path).suffix + ".metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return drafts


def main() -> None:
    """完成当前模块中的一个处理步骤。

参数：无。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    parser = argparse.ArgumentParser(description="基于真实案例生成法律候选题")
    parser.add_argument("--input", default=str(DATA_ROOT / "cleaned" / "structured_cases.jsonl"), help="结构化案件 JSONL")
    parser.add_argument("--output", default=str(DATA_ROOT / "drafts" / "candidate_questions.jsonl"), help="候选题 JSONL")
    parser.add_argument("--max-items", "--max-cases", type=int, default=None, help="只处理前 N 案")
    parser.add_argument("--cases", default="", help="只处理指定 case_id，逗号分隔")
    parser.add_argument("--questions-per-case", type=int, default=2, help="每案候选题数量")
    args = parser.parse_args()
    case_ids = {value.strip() for value in args.cases.split(",") if value.strip()} or None
    try:
        rows = run(args.input, args.output, args.max_items, case_ids, args.questions_per_case)
        print(f"完成：{args.output}，共 {len(rows)} 道待审候选题")
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

