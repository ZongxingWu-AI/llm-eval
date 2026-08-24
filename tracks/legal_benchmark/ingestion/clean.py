"""项目模块：tracks/legal_benchmark/ingestion/clean.py。

本文件属于三条评测线或公共工具层的一部分，负责完成本文件名对应的处理步骤。输入来自上游函数或数据目录，输出返回给下游函数或写入对应结果目录。

项目位置：tracks/legal_benchmark/ingestion/clean.py。
主要用途：法律真实案例 Benchmark，负责判决书解析、结构化提取、出题、校验和法律评测。
输入：输入来自法律线 data/raw、parsed、cleaned、drafts、releases 或 taxonomy/schema。
输出：输出按生命周期写入法律线对应 data 子目录或 results 目录。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：ingestion/extraction/generation/evaluation 可能写文件；只有带模型选项时才调用模型。
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from typing import Iterable

from core.data_io import write_jsonl
from tracks.legal_benchmark.paths import DATA_ROOT

PARSER_VERSION = "legal-parser-v3"
ROLE_LABELS = ("原告", "被告", "第三人", "申请人", "被申请人", "上诉人", "被上诉人", "委托诉讼代理人", "诉讼代理人", "法定代表人")
SECTION_MARKERS = {
    "claims": ("诉讼请求", "请求事项"),
    "defenses": ("被告辩称", "被告答辩", "答辩意见", "未作答辩"),
    "facts": ("经审理查明", "审理查明", "本院查明"),
    "court_reasoning": ("本院认为", "法院认为"),
    "judgment": ("判决如下", "裁判主文", "判决主文"),
}


def list_raw_files(raw_dir: str | Path) -> list[Path]:
    """列出原始判决书目录中的可处理文件。调用前是 raw 目录，调用后返回排序后的 md/txt 文件列表，并跳过 README。"""

    directory = Path(raw_dir)
    if not directory.exists():
        return []
    files: list[Path] = []
    for path in directory.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        if path.name.lower().startswith("readme."):
            continue
        files.append(path)
    return sorted(files)


def sha256_text(text: str) -> str:
    """计算原文 UTF-8 编码的 SHA-256。调用前是完整文本，调用后返回固定长度哈希，用于识别内容变化和建立来源清单。"""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_case_no(text: str) -> str:
    """从判决书全文提取案号。调用前是原始文本，调用后返回规范化的中文括号案号；找不到时返回空字符串。"""

    match = re.search(r"[（(]\d{4}[）)][^\n，。；;]{2,40}号", text)
    return match.group(0).replace("(", "（").replace(")", "）") if match else ""


def _extract_date(text: str) -> str:
    """为同一文件中的公开流程提供一个小而明确的辅助步骤。

参数：text。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    numeric = re.findall(r"\d{4}年\d{1,2}月\d{1,2}日", text)
    chinese = re.findall(r"[二〇零一二三四五六七八九十]{4}年[一二三四五六七八九十]{1,3}月[一二三四五六七八九十]{1,3}日", text)
    return (numeric + chinese)[-1] if numeric or chinese else ""


def _infer_procedure(case_no: str) -> str:
    """为同一文件中的公开流程提供一个小而明确的辅助步骤。

参数：case_no。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    for token, label in (("民初", "一审"), ("民终", "二审"), ("民再", "再审"), ("刑初", "一审"), ("行初", "一审")):
        if token in case_no:
            return label
    return ""


def _first_line_matching(text: str, pattern: str) -> str:
    """为同一文件中的公开流程提供一个小而明确的辅助步骤。

参数：text、pattern。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    for line in text.splitlines():
        if re.search(pattern, line):
            return re.sub(r"\s+", "", line.strip())
    return ""


def _split_party_names(value: str) -> list[str]:
    """为同一文件中的公开流程提供一个小而明确的辅助步骤。

参数：value。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    value = re.sub(r"（[^）]*）|\([^)]*\)", "", value).strip(" ：:、，,；;。\t")
    if not value:
        return []
    tokens = re.split(r"[、,，；;]\s*", value)
    names: list[str] = []
    descriptors = ("男", "女", "出生", "汉族", "住", "住所", "公民身份", "身份证", "统一社会信用", "律师", "负责人")
    for token in tokens:
        token = re.sub(r"\s+", "", token).strip("。；;")
        if not token:
            continue
        if any(token.startswith(prefix) for prefix in descriptors):
            break
        if len(token) > 40:
            token = re.split(r"(?:系|住|出生|公民身份|身份证)", token, maxsplit=1)[0]
        if token and token not in names:
            names.append(token)
    return names


def extract_parties(text: str) -> list[dict[str, str]]:
    """从带角色冒号的行中提取全部当事人和代理人。调用前是全文，调用后返回去重并带 party_id 的角色-姓名列表，不把叙述句误当成当事人。"""

    parties: list[dict[str, str]] = []
    for line in text.splitlines():
        clean_line = line.strip()
        for role in ROLE_LABELS:
            match = re.match(rf"{re.escape(role)}\s*[:：]\s*(.+)", clean_line)
            if not match:
                continue
            for name in _split_party_names(match.group(1)):
                parties.append({"party_id": "", "role": role, "name": name})
            break
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for party in parties:
        key = (party["role"], party["name"])
        if key not in seen:
            seen.add(key)
            party["party_id"] = f"party_{len(unique) + 1:02d}"
            unique.append(party)
    return unique


def _marker_positions(text: str) -> list[tuple[int, str, str]]:
    """为同一文件中的公开流程提供一个小而明确的辅助步骤。

参数：text。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    positions: list[tuple[int, str, str]] = []
    for section, markers in SECTION_MARKERS.items():
        section_matches: list[tuple[int, str, str]] = []
        for marker in markers:
            match = re.search(re.escape(marker), text)
            if match:
                section_matches.append((match.start(), marker, section))
        if section_matches:
            positions.append(min(section_matches))
    return sorted(positions)


def split_sections(text: str) -> dict[str, str]:
    """无损切分判决书主要章节。

    输入是完整原文，输出是包含 ``header``、诉讼请求、答辩、事实、证据、
    法院说理、判决主文和尾部信息的字典。原文片段仍保留在对应字段中，
    例如“本院认为”之后的内容进入 ``court_reasoning``，不会只保留摘要。
    不调用模型，也不写文件；章节缺失时保留空字符串，交给质量状态提示人工审核。
    """

    sections = {key: "" for key in ("header", "claims", "defenses", "facts", "evidence", "court_reasoning", "judgment", "tail")}
    positions = _marker_positions(text)
    if not positions:
        sections["header"] = text
        return sections
    sections["header"] = text[:positions[0][0]]
    for index, (start, _marker, section) in enumerate(positions):
        has_next = index + 1 < len(positions)
        if has_next:
            end = positions[index + 1][0]
        else:
            end = len(text)
        sections[section] = text[start:end]
    facts = sections["facts"]
    evidence_match = re.search(r"(?:以上事实|上述事实).{0,20}(?:证据|证明)", facts)
    if evidence_match:
        sections["evidence"] = facts[evidence_match.start():]
        sections["facts"] = facts[:evidence_match.start()]
    judgment = sections["judgment"]
    tail_match = re.search(r"(?:如不服本判决|审判长|审判员|书记员|本件与原本核对无异)", judgment)
    if tail_match:
        sections["tail"] = judgment[tail_match.start():]
        sections["judgment"] = judgment[:tail_match.start()]
    return sections


def extract_statutes(text: str) -> list[str]:
    """提取全文中出现的法律条文表达。调用前是完整文本，调用后返回去重后的法条列表。"""

    values = re.findall(r"《[^》]{2,100}》[^。；\n]{0,120}", text)
    unique_values: list[str] = []
    for value in values:
        cleaned = value.strip(" ，,：:")
        if cleaned and cleaned not in unique_values:
            unique_values.append(cleaned)
    return unique_values


def extract_amounts(text: str) -> list[str]:
    """提取金额及货币表达。调用前是完整文本，调用后返回金额字符串列表，供后续人工审核和题目生成参考。"""

    matches = re.findall(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*元", text)
    unique_values: list[str] = []
    for value in matches:
        if value not in unique_values:
            unique_values.append(value)
    return unique_values


def extract_dates(text: str) -> list[str]:
    """提取中文和数字日期表达。调用前是完整文本，调用后返回日期字符串列表。"""

    values = re.findall(r"\d{4}年\d{1,2}月\d{1,2}日", text)
    values += re.findall(r"[二〇零一二三四五六七八九十]{4}年[一二三四五六七八九十]{1,3}月[一二三四五六七八九十]{1,3}日", text)
    unique_values: list[str] = []
    for value in values:
        if value not in unique_values:
            unique_values.append(value)
    return unique_values


def extract_interest_expressions(text: str) -> list[str]:
    """提取包含利息、利率、LPR 或迟延履行利息的句子。调用前是完整文本，调用后返回相关表达列表。"""

    patterns = [r"[^。；\n]{0,50}(?:利息|利率|LPR|贷款市场报价利率)[^。；\n]{0,100}"]
    values: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = match.group(0).strip()
            if value and value not in values:
                values.append(value)
    return values


def infer_category(text: str) -> str:
    """完成当前模块中的一个处理步骤。

参数：text。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    rules = (("劳动争议", ("劳动关系", "劳动合同", "工资", "工伤", "经济补偿")),
             ("婚姻家庭、继承纠纷", ("离婚", "抚养", "继承", "夫妻共同债务", "婚姻")),
             ("侵权责任纠纷", ("机动车交通事故", "医疗损害", "侵权责任", "人身损害", "安全保障义务")),
             ("物权纠纷", ("物权", "所有权", "返还原物", "排除妨害", "相邻关系")),
             ("合同、准合同纠纷", ("合同", "货款", "借款", "租赁", "买卖", "服务费")))
    for category, keywords in rules:
        for keyword in keywords:
            if keyword in text:
                return category
    return "未分类"


def infer_cause_path(text: str, category: str) -> list[str]:
    """完成当前模块中的一个处理步骤。

参数：text、category。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    leaves = {
        "合同、准合同纠纷": (("买卖", "买卖合同纠纷"), ("借款", "民间借贷纠纷"), ("租赁", "租赁合同纠纷"), ("服务", "服务合同纠纷"), ("劳务", "劳务合同纠纷")),
        "劳动争议": (("劳动关系", "确认劳动关系纠纷"), ("工资", "劳动报酬纠纷"), ("解除", "解除劳动合同纠纷"), ("经济补偿", "经济补偿金纠纷"), ("工伤", "工伤保险待遇纠纷")),
        "侵权责任纠纷": (("交通事故", "机动车交通事故责任纠纷"), ("医疗", "医疗损害责任纠纷"), ("产品", "产品责任纠纷"), ("安全保障", "违反安全保障义务责任纠纷"), ("人身损害", "人身损害赔偿纠纷")),
        "婚姻家庭、继承纠纷": (("离婚后财产", "离婚后财产纠纷"), ("离婚", "离婚纠纷"), ("抚养", "抚养纠纷"), ("继承", "继承纠纷"), ("共同债务", "夫妻共同债务纠纷")),
        "物权纠纷": (("所有权确认", "所有权确认纠纷"), ("返还原物", "返还原物纠纷"), ("排除妨害", "排除妨害纠纷"), ("相邻", "相邻关系纠纷"), ("房屋", "房屋所有权纠纷")),
    }
    if category == "未分类":
        return []
    default_leaves = {
        "合同、准合同纠纷": "其他合同纠纷",
        "劳动争议": "其他劳动争议",
        "侵权责任纠纷": "其他侵权责任纠纷",
        "婚姻家庭、继承纠纷": "其他婚姻家庭、继承纠纷",
        "物权纠纷": "其他物权纠纷",
    }
    leaf = default_leaves[category]
    for keyword, label in leaves.get(category, ()):
        if keyword in text:
            leaf = label
            break
    return [category, leaf]


def _party_name_length(party: dict) -> int:
    """返回当事人名称长度，供匿名化排序使用。

    输入：一个包含 ``name`` 字段的当事人字典。
    输出：名称的字符数；名称缺失或类型不正确时返回 0。
    运行前数据形态：当事人列表尚未排序。
    运行后数据变化：不修改字典，只提供稳定的排序键。
    副作用：不写文件、不调用模型。
    异常或失败处理：名称不是字符串时按空名称处理。
    """
    name = party.get("name", "")
    if not isinstance(name, str):
        return 0
    return len(name)


def anonymize_text(text: str, parties: Iterable[dict[str, str]]) -> str:
    """完成当前模块中的一个处理步骤。

参数：text、parties。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    result = text
    sorted_parties = sorted(parties, key=_party_name_length, reverse=True)
    for index, party in enumerate(sorted_parties, start=1):
        if len(party["name"]) >= 2:
            result = result.replace(party["name"], f"当事人{index}")
    return result


def parse_judgment(text: str, source_file: str = "") -> dict:
    """把一份原始判决书转换为无损结构化案件。

    调用前输入仍是原始全文；调用后会新增 ``case_id``、来源哈希、文书信息、
    多方当事人、章节、金额、日期、法条、分类和质量状态。
    ``full_text`` 与 ``sections`` 同时保留，``facts_summary`` 只是派生字段，
    不能替代全文。此函数只做确定性解析，不调用模型，但会计算哈希和当前处理时间。
    """

    case_no = extract_case_no(text)
    digest = sha256_text(text)
    parties = extract_parties(text)
    sections = split_sections(text)
    category = infer_category(text)
    procedure_stage = _infer_procedure(case_no)
    document_type = "判决书" if re.search(r"判\s*决\s*书", text) else ""
    domain = "民事" if "民" in case_no or "民事" in text else ""

    required_sections = ("claims", "facts", "court_reasoning", "judgment")
    missing_sections: list[str] = []
    for key in required_sections:
        if not sections[key]:
            missing_sections.append(key)

    document = {
        "case_no": case_no,
        "court": _first_line_matching(text, r"人民法院"),
        "judgment_date": _extract_date(text),
        "document_type": document_type,
        "procedure_stage": procedure_stage,
    }
    classification = {
        "domain": domain,
        "procedure_stage": procedure_stage,
        "document_type": document_type,
        "primary_category": category,
        "cause_path": infer_cause_path(text, category),
        "legal_issues": [],
        "procedure_tags": [],
        "evidence_tags": [],
    }
    quality = {
        "parser_version": PARSER_VERSION,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "review_status": "pending",
        "status": "needs_review" if missing_sections else "parsed",
        "missing_sections": missing_sections,
    }
    return {
        "case_id": "case_" + digest[:12],
        "source": {
            "source_file": source_file,
            "source_url": "",
            "sha256": digest,
            "retrieved_at": "",
            "reuse_status": "local_only",
        },
        "document": document,
        "parties": parties,
        "full_text": text,
        "anonymized_text": anonymize_text(text, parties),
        "sections": sections,
        "facts_summary": sections.get("facts", "").strip(),
        "cited_statutes": extract_statutes(text),
        "amounts": extract_amounts(text),
        "dates": extract_dates(text),
        "interest_expressions": extract_interest_expressions(text),
        "classification": classification,
        "quality": quality,
    }


def clean_directory(raw_dir: str | Path = DATA_ROOT / "raw", output_path: str | Path = DATA_ROOT / "parsed" / "parsed_judgments.jsonl",
                    max_items: int | None = None, manifest_output: str | Path | None = None) -> list[dict]:
    """批量解析 raw 目录并写出 parsed JSONL 与来源 manifest。

    调用前输入是一个包含 ``.md`` 或 ``.txt`` 原始判决书的目录；调用后返回
    案件字典列表，并把完整解析结果和每案哈希分别写入输出路径。每次运行都会
    根据当前文件内容重新计算哈希和 ``case_id``，所以同名文件内容变化时不会被错误跳过。
    """

    files = list_raw_files(raw_dir)
    if max_items is not None and max_items > 0:
        files = files[:max_items]
    rows: list[dict] = []
    for path in files:
        text = path.read_text(encoding="utf-8-sig")
        rows.append(parse_judgment(text, path.name))
    write_jsonl(output_path, rows)

    if manifest_output:
        manifest_path = Path(manifest_output)
    else:
        manifest_path = DATA_ROOT / "manifests" / "raw_manifest.jsonl"
    manifests: list[dict] = []
    for row in rows:
        source = row["source"]
        quality = row["quality"]
        manifests.append({
            "case_id": row["case_id"],
            "source_file": source["source_file"],
            "sha256": source["sha256"],
            "source_url": source["source_url"],
            "retrieved_at": source["retrieved_at"],
            "reuse_status": "local_only",
            "review_status": quality["review_status"],
        })
    write_jsonl(manifest_path, manifests)
    return rows


def main() -> None:
    """完成当前模块中的一个处理步骤。

参数：无。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    parser = argparse.ArgumentParser(description="无损解析本地民事判决书")
    parser.add_argument("--raw-dir", "--input", default=str(DATA_ROOT / "raw"), help="原始判决书目录")
    parser.add_argument("--output", default=str(DATA_ROOT / "parsed" / "parsed_judgments.jsonl"), help="解析结果 JSONL")
    parser.add_argument("--manifest-output", default=str(DATA_ROOT / "manifests" / "raw_manifest.jsonl"), help="本地来源清单 JSONL")
    parser.add_argument("--max-items", "--max-cases", type=int, default=None, help="只处理前 N 份")
    args = parser.parse_args()
    rows = clean_directory(args.raw_dir, args.output, args.max_items, args.manifest_output)
    print(f"完成：{args.output}，共 {len(rows)} 份；manifest：{args.manifest_output}")


if __name__ == "__main__":
    main()


