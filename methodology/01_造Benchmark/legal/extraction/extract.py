"""法律结构化信息提取模块。

项目位置：法律真实案例评测线的 extraction 阶段。
输入：ingestion 生成的 parsed_judgments.jsonl，其中包含完整原文和章节。
输出：structured_cases.jsonl，每案新增可回溯的 legal_extraction；同时写运行元数据。
上下游：上游是无损解析，下游是 generation.generate 的候选题生成。
副作用：覆盖指定 cleaned JSONL；默认只用规则，传入 --use-llm 时才调用 EXTRACTOR 模型。"""
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
from core.project_paths import LEGAL_DATA_ROOT as DATA_ROOT, LEGAL_PROMPT_ROOT as PROMPT_ROOT

EXTRACTOR_VERSION = "legal-extractor-v1"
DEFAULT_PARSED_INPUT = DATA_ROOT / "parsed" / "parsed_judgments_selected_50.jsonl"


def _sentences(text: str) -> list[str]:
    """用途：把一个法律章节切成可逐句扫描且仍可回到原文定位的句子列表。

    输入：text 是 claims、facts、court_reasoning 或 judgment 的章节字符串。
    输出：返回去除空白片段后的句子列表。
    运行前数据形态：运行前是包含换行和句号的一段文本。
    运行后数据变化：运行后每个非空句子成为独立字符串，source_quote 仍能在原章节找到。
    副作用：只处理内存，不修改章节、不写文件、不调用模型。
    异常或失败处理：空文本返回空列表。"""

    parts = re.split(r"(?<=[。！？；])\s*|\n+", text)
    sentences: list[str] = []
    for part in parts:
        cleaned = part.strip()
        if cleaned:
            sentences.append(cleaned)
    return sentences


def deterministic_extract(case: dict) -> dict:
    """用途：用可重复规则从法院说理和判决主文提取法律争议、证据判断和结论。

    输入：case 是 ingestion 阶段产生且包含 sections 的案件字典。
    输出：返回 legal_issues、evidence_findings、conclusions 三组结构化字段。
    运行前数据形态：运行前案件只有原文章节。
    运行后数据变化：运行后每条证据判断和结论都带 source_section 与 source_quote。
    副作用：只读取案件字典，不写文件、不调用模型。
    异常或失败处理：章节缺失时对应列表为空，不生成无来源结论。
    最小示例：判决主文中的一句会成为 conclusion，引用字段保存同一句原文。"""

    sections = case.get("sections", {})
    reasoning = sections.get("court_reasoning", "")
    judgment = sections.get("judgment", "")
    conclusions: list[dict] = []
    conclusion_keywords = ("支持", "不予支持", "确认", "认定", "调整为", "承担", "判决")
    for section_name, section_text in (("court_reasoning", reasoning), ("judgment", judgment)):
        for sentence in _sentences(section_text):
            is_judgment = section_name == "judgment"
            has_keyword = False
            for keyword in conclusion_keywords:
                if keyword in sentence:
                    has_keyword = True
                    break
            if is_judgment or has_keyword:
                conclusions.append({
                    "conclusion": sentence,
                    "source_section": section_name,
                    "source_quote": sentence,
                })

    evidence_findings: list[dict] = []
    evidence_keywords = ("证据", "证据链", "证明", "不足以", "举证")
    for sentence in _sentences(reasoning):
        has_evidence_keyword = False
        for keyword in evidence_keywords:
            if keyword in sentence:
                has_evidence_keyword = True
                break
        if has_evidence_keyword:
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
    """用途：过滤无法通过章节名和原文短引定位的模型提取项。

    输入：items 是模型返回的候选字典列表；sections 是案件章节映射。
    输出：返回 source_quote 确实出现在指定 source_section 中的字典列表。
    运行前数据形态：运行前模型结论可能含幻觉引用。
    运行后数据变化：运行后只保留可回溯到原判决章节的结论。
    副作用：只处理内存，不写文件、不调用模型。
    异常或失败处理：items 类型错误、字段缺失、章节不存在或引用不在原文时跳过该项。
    最小示例：source_section=court_reasoning 且 quote 在该章节中时保留，否则过滤。"""

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
    """用途：为单个 parsed 案件生成 legal_extraction，并在启用客户端时融合有来源的大模型结果。

    输入：case 是 parsed 案件；client/model 为空时只走规则路径。
    输出：返回案件浅拷贝，并新增 legal_extraction 和 extractor_version。
    运行前数据形态：运行前包含 sections、classification 等解析字段。
    运行后数据变化：运行后增加争议焦点、证据判断和法院结论，原 full_text 与 sections 不变。
    副作用：client 存在时会加载 Prompt 并调用模型；本函数本身不写文件。
    异常或失败处理：模型异常或 JSON 解析失败时保留确定性提取；无来源的模型项被过滤。
    最小示例：client=None 时输出完全由 deterministic_extract 产生。"""

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
            legal_issues: list[str] = []
            for value in candidate.get("legal_issues", []):
                issue = str(value).strip()
                if issue:
                    legal_issues.append(issue)
            extracted = {
                "legal_issues": legal_issues,
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


def run(input_path: str | Path = DEFAULT_PARSED_INPUT,
        output_path: str | Path = DATA_ROOT / "cleaned" / "structured_cases.jsonl",
        max_items: int | None = None, use_llm: bool = False) -> list[dict]:
    """用途：批量读取 parsed JSONL，执行结构化法律提取并写入 cleaned JSONL 和运行元数据。

    输入：input_path、output_path、max_items 控制数据；use_llm 决定是否配置 EXTRACTOR 模型。
    输出：返回清洗后案件列表，并写 structured_cases.jsonl 及相邻 metadata.json。
    运行前数据形态：运行前每行是 parsed 案件。
    运行后数据变化：运行后每行新增 legal_extraction，元数据记录数量、模型和路径。
    副作用：读取 JSONL、创建目录并覆盖输出；仅 use_llm=True 时读取环境变量并调用模型。
    异常或失败处理：模型角色未配置或单案失败时按现有异常策略处理；max_items 只截取本次试跑。"""

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
    """用途：提供结构化提取 CLI，把输入、输出、试跑数量和 --use-llm 传给 run。

    输入：参数来自 argparse，默认从 data/parsed 读取并写 data/cleaned。
    输出：成功打印案件数；失败打印错误并以状态码 1 退出。
    运行前数据形态：运行前是命令行参数。
    运行后数据变化：运行后生成可供候选题生成使用的 structured_cases.jsonl。
    副作用：会覆盖指定 cleaned JSONL 和元数据；只有 --use-llm 时调用模型。
    异常或失败处理：参数错误由 argparse 处理；run 抛出的异常转换为非零退出。"""

    parser = argparse.ArgumentParser(description="提取带原文定位的法律结构化信息")
    parser.add_argument("--input", default=str(DEFAULT_PARSED_INPUT), help="解析后案件 JSONL")
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


