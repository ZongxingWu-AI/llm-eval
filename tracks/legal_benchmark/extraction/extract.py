"""项目模块：tracks/legal_benchmark/extraction/extract.py。

本文件属于三条评测线或公共工具层的一部分，负责完成本文件名对应的处理步骤。输入来自上游函数或数据目录，输出返回给下游函数或写入对应结果目录。

项目位置：tracks/legal_benchmark/extraction/extract.py。
主要用途：法律真实案例 Benchmark，负责判决书解析、结构化提取、出题、校验和法律评测。
输入：输入来自法律线 data/raw、parsed、cleaned、drafts、releases 或 taxonomy/schema。
输出：输出按生命周期写入法律线对应 data 子目录或 results 目录。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：ingestion/extraction/generation/evaluation 可能写文件；只有带模型选项时才调用模型。
"""
import argparse
import json
import re
import sys
from pathlib import Path

from core import llm_client
from core.data_io import read_jsonl, write_jsonl
from core.json_utils import parse_json_object
from core.prompt_loader import load_template, render
from core.run_metadata import new_run_metadata
from tracks.legal_benchmark.paths import DATA_ROOT, PROMPT_ROOT

EXTRACTOR_VERSION = "legal-extractor-v1"


def _sentences(text: str) -> list[str]:
    """把章节文本切成适合规则扫描的句子列表。

    输入是一个章节字符串，输出会去除首尾空白并跳过空片段；不写文件，
    也不改变原始字符串。这样后续提取出的 ``source_quote`` 可以直接回到章节中定位。
    """

    parts = re.split(r"(?<=[。！？；])\s*|\n+", text)
    sentences: list[str] = []
    for part in parts:
        cleaned = part.strip()
        if cleaned:
            sentences.append(cleaned)
    return sentences


def deterministic_extract(case: dict) -> dict:
    """使用确定性规则提取争议焦点、证据判断和法院结论。

    输入是 parsed 案件，输出是 ``legal_issues``、``evidence_findings`` 和
    ``conclusions`` 三组字段。每条证据判断和结论都带 ``source_section``、
    ``source_quote``，例如法院说理中的一句“本院认为……”会原样放入引用字段。
    函数不调用模型、不写文件，适合作为模型提取失败时的可重复回退路径。
    """

    sections = case.get("sections", {})
    reasoning = sections.get("court_reasoning", "")
    judgment = sections.get("judgment", "")
    conclusions: list[dict] = []
    conclusion_keywords = ("支持", "不予支持", "确认", "认定", "调整为", "承担", "判决")
    for section_name, section_text in (("court_reasoning", reasoning), ("judgment", judgment)):
        for sentence in _sentences(section_text):
            is_judgment = section_name == "judgment"
            has_keyword = any(key in sentence for key in conclusion_keywords)
            if is_judgment or has_keyword:
                conclusions.append({
                    "conclusion": sentence,
                    "source_section": section_name,
                    "source_quote": sentence,
                })

    evidence_findings: list[dict] = []
    evidence_keywords = ("证据", "证据链", "证明", "不足以", "举证")
    for sentence in _sentences(reasoning):
        if any(key in sentence for key in evidence_keywords):
            evidence_findings.append({
                "conclusion": sentence,
                "source_section": "court_reasoning",
                "source_quote": sentence,
            })

    issues: list[str] = []
    for sentence in _sentences(reasoning):
        if sentence.startswith("关于"):
            issues.append(sentence[:80])
    return {"legal_issues": issues, "evidence_findings": evidence_findings, "conclusions": conclusions}


def _valid_grounded_items(items, sections: dict) -> list[dict]:
    """为同一文件中的公开流程提供一个小而明确的辅助步骤。

参数：items、sections。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    valid: list[dict] = []
    if not isinstance(items, list):
        return valid
    for item in items:
        if not isinstance(item, dict):
            continue
        section = item.get("source_section", "")
        quote = item.get("source_quote", "")
        section_text = sections.get(section, "")
        if section in sections and quote and quote in section_text:
            valid.append(item)
    return valid


def extract_case(case: dict, client=None, model: str = "") -> dict:
    """为一个案件补充带来源定位的结构化法律信息。

    调用前案件已经包含 ``full_text`` 和 ``sections``；调用后复制案件并新增
    ``legal_extraction`` 与提取质量元数据。默认使用规则提取；传入客户端时才调用模型，
    且模型返回的每条结论必须能用 ``source_quote`` 在指定章节中找到，否则丢弃并记录错误。
    因此即使模型输出不稳定，原文和规则提取结果仍保留。
    """

    extracted = deterministic_extract(case)
    method = "rules"
    errors: list[str] = []
    if client is not None:
        template = load_template("legal_extraction_prompt.md", PROMPT_ROOT)
        prompt = render(template, {"case_sections": json.dumps(case.get("sections", {}), ensure_ascii=False)})
        try:
            raw = llm_client.call_model(client, model, prompt, 0, 8192)[0]
            candidate = parse_json_object(raw)
            sections = case.get("sections", {})
            llm_conclusions = _valid_grounded_items(candidate.get("conclusions", []), sections)
            llm_evidence = _valid_grounded_items(candidate.get("evidence_findings", []), sections)
            extracted = {
                "legal_issues": [str(value) for value in candidate.get("legal_issues", []) if str(value).strip()],
                "evidence_findings": llm_evidence,
                "conclusions": llm_conclusions,
            }
            method = "llm_grounded"
            if len(llm_conclusions) < len(candidate.get("conclusions", [])):
                errors.append("已丢弃无法在原章节定位的模型结论")
        except Exception as exc:
            errors.append(f"模型提取失败，已回退规则提取：{exc}")
    result = dict(case)
    result["legal_extraction"] = extracted
    result.setdefault("classification", {})["legal_issues"] = extracted["legal_issues"]
    result.setdefault("quality", {})["extraction"] = {
        "version": EXTRACTOR_VERSION, "method": method, "status": "needs_review", "errors": errors
    }
    return result


def run(input_path: str | Path = DATA_ROOT / "parsed" / "parsed_judgments.jsonl",
        output_path: str | Path = DATA_ROOT / "cleaned" / "structured_cases.jsonl",
        max_items: int | None = None, use_llm: bool = False) -> list[dict]:
    """完成当前模块中的一个处理步骤。

参数：input_path、output_path、max_items、use_llm。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    rows = read_jsonl(input_path)
    if max_items is not None and max_items > 0:
        rows = rows[:max_items]
    client = None
    model = ""
    if use_llm:
        llm_client.load_env()
        base, key, model = llm_client.read_role("EXTRACTOR", "deepseek-v4-flash")
        client = llm_client.build_client(base, key)
    results: list[dict] = []
    for row in rows:
        results.append(extract_case(row, client, model))
    write_jsonl(output_path, results)
    target = Path(output_path)
    metadata = new_run_metadata("legal_benchmark.extraction", input=str(input_path), output=str(output_path),
                                count=len(results), method="llm_grounded" if use_llm else "rules", model=model)
    target.with_suffix(target.suffix + ".metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def main() -> None:
    """完成当前模块中的一个处理步骤。

参数：无。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    parser = argparse.ArgumentParser(description="提取带原文定位的法律结构化信息")
    parser.add_argument("--input", default=str(DATA_ROOT / "parsed" / "parsed_judgments.jsonl"), help="解析后案件 JSONL")
    parser.add_argument("--output", default=str(DATA_ROOT / "cleaned" / "structured_cases.jsonl"), help="结构化案件 JSONL")
    parser.add_argument("--max-items", "--max-cases", type=int, default=None, help="只处理前 N 案")
    parser.add_argument("--use-llm", action="store_true", help="使用模型提取；不传则使用可重复的规则提取")
    args = parser.parse_args()
    try:
        rows = run(args.input, args.output, args.max_items, args.use_llm)
        print(f"完成：{args.output}，共 {len(rows)} 案")
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
