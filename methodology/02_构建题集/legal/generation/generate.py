"""法律候选题生成模块。

项目位置：法律真实案例评测线的 generation 阶段。
输入：extract 阶段中已解析并带来源定位的案件 JSONL。
输出：命令行指定的 drafts JSONL、错误 JSONL 和运行元数据；新题默认 review_status=pending。
上下游：上游是结构化提取，下游是人工审稿和 dataset.build。
副作用：读取 GENERATOR 模型配置并调用模型，覆盖指定 drafts 输出；不修改案件原文。"""

import argparse
import importlib
import json
import sys
from pathlib import Path

from core import llm_client
from core.data_io import read_jsonl, write_jsonl
from core.json_utils import parse_json_value
from core.prompt_loader import load_template, render
from core.run_metadata import new_run_metadata
from core.project_paths import LEGAL_PROMPT_ROOT as PROMPT_ROOT
# Taxonomy 属于“造 Benchmark”环节；目录名含中文和数字，使用字符串导入。
_taxonomy = importlib.import_module("methodology.01_造Benchmark.legal.taxonomy")
load_taxonomy = _taxonomy.load_taxonomy

REQUIRED_FIELDS = ("primary_issue", "task_type", "reasoning_capabilities", "answer_type", "scoring_method",
                   "difficulty", "risk_level", "question", "reference_answer", "rubric", "source_evidence")


def _valid_evidence(case: dict, evidence) -> list[dict]:
    """用途：校验候选题引用的证据是否真实存在于案件指定章节。

    输入：case 是结构化案件；evidence 是模型返回的 source_evidence 候选列表。
    输出：返回具有有效 source_section 和 source_quote 的证据字典列表。
    运行前数据形态：运行前证据可能来自不受信任的模型 JSON。
    运行后数据变化：运行后只保留人工可沿章节回查的短引用。
    副作用：只处理内存，不写文件、不调用模型。
    异常或失败处理：类型错误、空引用、章节不存在或引用不在原文时过滤。"""

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
    """用途：调用 GENERATOR 模型为单个真实案件生成待人工审核的候选问题。

    输入：case 是 extract 案件；client/model 是模型配置；questions_per_case 是期望数量。
    输出：返回 (有效候选题列表, 错误消息列表)，候选题统一带 case_id、case_classification 和 review_status=pending。
    运行前数据形态：运行前是一条含 sections 与 legal_extraction 的案件。
    运行后数据变化：运行后得到可追溯但尚未获准发布的 pending 候选题。
    副作用：会加载出题 Prompt 并调用模型；本函数不直接写文件。
    异常或失败处理：模型调用或 JSON 解析失败由调用方捕获；缺必填字段、无有效证据或数量超限会记录错误并过滤。
    最小示例：模型返回两题时逐题校验字段和 source_evidence，合格项才进入 drafts。"""

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


def run(input_path: str | Path, output_path: str | Path,
        max_items: int | None = None, case_ids: set[str] | None = None, questions_per_case: int = 2) -> list[dict]:
    """用途：批量调用出题模型，把 extract 案件转换为候选题、错误记录和运行元数据。

    输入：input_path、output_path、max_items、case_ids、questions_per_case 控制本次任务。
    输出：返回候选题列表；写指定 drafts JSONL、.errors.jsonl 和 .metadata.json。
    运行前数据形态：运行前每行是一条 extract 案件。
    运行后数据变化：运行后每道合格题成为 JSONL 一行，状态仍为 pending，不能直接作为 release。
    副作用：读取环境变量并调用 GENERATOR 模型，创建目录并覆盖三个输出文件。
    异常或失败处理：单案异常写入错误文件后继续其他案件；模型配置缺失或全局文件错误会抛出。"""

    cases = read_jsonl(input_path)
    if case_ids:
        selected_cases: list[dict] = []
        for case in cases:
            if case.get("case_id") in case_ids:
                selected_cases.append(case)
        cases = selected_cases
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
            for error in case_errors:
                errors.append({"case_id": case.get("case_id"), "error": error})
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
    """用途：提供候选题生成 CLI，解析案件筛选、最大案件数和每案题数后调用 run。

    输入：参数来自 argparse；--cases 是逗号分隔 case_id。
    输出：成功打印待审题数；失败打印错误并以状态码 1 退出。
    运行前数据形态：运行前是命令行筛选参数。
    运行后数据变化：运行后生成供人工审稿和 dataset.build 使用的候选题文件。
    副作用：会调用 GENERATOR 模型并覆盖 drafts、errors 和 metadata 输出。
    异常或失败处理：参数错误由 argparse 处理；run 异常转换为非零退出。"""

    parser = argparse.ArgumentParser(description="基于真实案例生成法律候选题")
    parser.add_argument("--input", required=True, help="extract 阶段案件 JSONL")
    parser.add_argument("--output", required=True, help="候选题 JSONL")
    parser.add_argument("--max-items", "--max-cases", type=int, default=None, help="只处理前 N 案")
    parser.add_argument("--cases", default="", help="只处理指定 case_id，逗号分隔")
    parser.add_argument("--questions-per-case", type=int, default=2, help="每案候选题数量")
    args = parser.parse_args()
    selected_case_ids: set[str] = set()
    for value in args.cases.split(","):
        cleaned_value = value.strip()
        if cleaned_value:
            selected_case_ids.add(cleaned_value)
    case_ids = selected_case_ids or None
    try:
        rows = run(args.input, args.output, args.max_items, case_ids, args.questions_per_case)
        print(f"完成：{args.output}，共 {len(rows)} 道待审候选题")
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
