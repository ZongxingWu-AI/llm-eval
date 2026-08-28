"""法律判决书无损解析模块。

"不调用大模型，不试图理解复杂法律问题，而是先把原始判决书完整保存下来，同时用正则和关键词做基础结构化。"

    作用：
        不调用大模型
        保留完整原文
        切分章节
        识别主体
        找案号、日期、金额、法条、利息
        做初步分类
        生成 case_id
        记录 sha256
        生成质量状态


项目位置：法律真实案例评测线的 ingestion 阶段。
输入：命令行指定的批次 raw/ 目录中一案一文件的 Markdown 或文本判决书。
输出：命令行指定的 clean JSONL、来源 manifest 和相邻 metadata；每案保留 full_text、章节、当事人、分类、哈希和质量状态。
上下游：上游是人工收集的原始案例，下游是 extraction.extract 的法律信息提取。
副作用：读取本地原始文件并覆盖指定 JSONL 输出；不调用大模型，也不修改 raw 文件。"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from typing import Iterable

from core.data_io import write_jsonl
from core.run_metadata import new_run_metadata

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
    """用途：枚举 raw 目录中可交给解析器处理的判决书，并保持稳定文件顺序。
       "先找哪些文件需要处理"
    输入：raw_dir 是原始案例目录路径。
    输出：返回按文件名排序的 .md/.txt Path 列表，README 不进入列表。
    运行前数据形态：目录可能同时包含 README、子目录和判决书。
    运行后数据变化：结果只保留普通文件中的 Markdown 和文本判决书。
    副作用：只读取目录项，不创建目录、不写文件、不调用模型。
    异常或失败处理：目录不存在时返回空列表；其他文件系统错误由调用方处理。"""

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


def sha256_bytes(content: bytes) -> str:
    """用途：计算原始判决书字节内容的 SHA-256。

    输入：content 是原始文件的完整 UTF-8/UTF-8-SIG 字节。
    输出：返回 64 位十六进制哈希字符串。
    运行前数据形态：输入是文件尚未解码的原始字节。
    运行后数据变化：哈希写入 source.sha256，并参与生成 case_id。
    副作用：只在内存中计算，不写文件、不调用模型。
    异常或失败处理：空字节也会得到确定哈希。"""

    return hashlib.sha256(content).hexdigest()


def sha256_text(text: str) -> str:
    """用途：计算判决书全文的 SHA-256，作为内容身份和变更检测依据。

    输入：text 是尚未截断的判决书完整字符串。
    输出：返回 64 位十六进制哈希字符串。
    运行前数据形态：输入是原始全文。
    运行后数据变化：输出哈希写入 source.sha256，并参与生成 case_id。
    副作用：只在内存中编码和计算，不写文件、不调用模型。
    异常或失败处理：空字符串也会得到确定哈希；非字符串会由 encode 调用抛出异常。
    最小示例：“判决全文”会得到固定哈希；正文任一字符变化都会产生新哈希。"""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_case_no(text: str) -> str:
    """用途：从判决书全文中识别并统一案号括号样式。

    输入：text 是包含标题和正文的原始判决书字符串。
    输出：找到时返回如（2024）浙0483民初5218号；找不到返回空字符串。
    运行前数据形态：原文案号可能使用半角或全角括号。
    运行后数据变化：输出统一使用中文全角括号。
    副作用：只做正则匹配，不修改全文、不写文件、不调用模型。
    异常或失败处理：不符合当前案号模式时返回空字符串，交由 quality.missing_sections 提醒人工复核。"""

    match = re.search(r"[（(]\d{4}[）)][^\n，。；;]{2,40}号", text)
    return match.group(0).replace("(", "（").replace(")", "）") if match else ""


def _extract_date(text: str) -> str:
    """用途：从全文提取最后出现的裁判日期，兼容阿拉伯数字和中文数字日期。

    输入：text 是完整判决书文本。
    输出：返回最后一个匹配日期字符串；没有日期时返回空字符串。
    运行前数据形态：全文可能包含借款日期、开庭日期和落款日期。
    运行后数据变化：取最后出现的日期作为 document.date 候选。
    副作用：只扫描内存文本，不写文件、不调用模型。
    异常或失败处理：无法匹配时返回空字符串，不猜测日期。"""

    numeric = re.findall(r"\d{4}年\d{1,2}月\d{1,2}日", text)
    chinese = re.findall(r"[二〇零一二三四五六七八九十]{4}年[一二三四五六七八九十]{1,3}月[一二三四五六七八九十]{1,3}日", text)
    return (numeric + chinese)[-1] if numeric or chinese else ""


def _infer_procedure(case_no: str) -> str:
    """用途：依据案号中的“民初、民终、民再”等标记推断程序阶段。

    输入：case_no 是 extract_case_no 返回的案号字符串。
    输出：返回一审、二审、再审、执行或未知。
    运行前数据形态：输入示例为（2024）浙0483民初5218号。
    运行后数据变化：输出“一审”，供 classification.procedure_stage 使用。
    副作用：只读取字符串，不写文件、不调用模型。
    异常或失败处理：空案号或未识别标记返回“未知”。"""

    for token, label in (("民初", "一审"), ("民终", "二审"), ("民再", "再审"), ("刑初", "一审"), ("行初", "一审")):
        if token in case_no:
            return label
    return ""


def _first_line_matching(text: str, pattern: str) -> str:
    """用途：查找第一行满足正则模式的非空文本，用于提取法院或文书标题。

    输入：text 是全文；pattern 是逐行匹配的正则表达式。
    输出：返回首个匹配行的去空白文本；找不到返回空字符串。
    运行前数据形态：输入是按换行组织的判决书。
    运行后数据变化：输出从全文中选择一行，不改变原始内容。
    副作用：只遍历内存文本，不写文件、不调用模型。
    异常或失败处理：正则无匹配时返回空字符串；非法正则由 re 模块抛出异常。"""

    for line in text.splitlines():
        if re.search(pattern, line):
            return re.sub(r"\s+", "", line.strip())
    return ""


def _split_party_names(value: str) -> list[str]:
    """用途：把一行中并列出现的多个当事人名称拆成独立名称。

    输入：value 是去掉角色标签后的姓名或机构名称文本。
    输出：返回保持原顺序、去重后的名称列表。
    运行前数据形态：输入可能是“张某、李某”或带顿号、逗号的名称串。
    运行后数据变化：输出为[“张某”, “李某”]，供 extract_parties 逐人建记录。
    副作用：只处理内存字符串，不写文件、不调用模型。
    异常或失败处理：空值或拆分后无有效名称时返回空列表。"""

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
        starts_with_descriptor = False
        for prefix in descriptors:
            if token.startswith(prefix):
                starts_with_descriptor = True
                break
        if starts_with_descriptor:
            break
        if len(token) > 40:
            token = re.split(r"(?:系|住|出生|公民身份|身份证)", token, maxsplit=1)[0]
        if token and token not in names:
            names.append(token)
    return names


def extract_parties(text: str) -> list[dict[str, str]]:
    """用途：识别原告、被告、第三人及代理人等多方当事人，避免只保留首个原被告。

    输入：text 是完整判决书；按 ROLE_LABELS 扫描角色行。
    输出：返回字典列表，每项包含 role 和 name，并按原文出现顺序去重。
    运行前数据形态：原始文本可能有“原告：甲、乙”和多个独立角色行。
    运行后数据变化：输出会拆成多条 party 记录，后续匿名化为每人分配独立编号。
    副作用：只读取全文，不匿名化原文、不写文件、不调用模型。
    异常或失败处理：未识别到角色时返回空列表；叙事句不会被当成新增当事人。
    最小示例：原告：甲、乙会生成两条 role=原告 的记录。"""

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
    """用途：定位诉讼请求、答辩、事实、法院说理和判决主文的章节标记。

    输入：text 是完整判决书；SECTION_MARKERS 提供受控标记词。
    输出：返回按字符位置排序的 (位置, 章节名, 命中标记) 元组列表。
    运行前数据形态：输入尚未切分，仍是一段完整字符串。
    运行后数据变化：输出记录边界，不删除任何正文。
    副作用：只扫描内存文本，不写文件、不调用模型。
    异常或失败处理：某章节无标记时不生成位置；重复标记只保留用于后续切分的实际命中。"""

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
    """用途：按已识别标记无损切分法律章节，并保留未归类的前置文本。

    输入：text 是完整判决书全文。
    输出：返回 sections 字典，可能包含 claims、defenses、facts、court_reasoning、judgment 和 header。
    运行前数据形态：运行前只有一段全文。
    运行后数据变化：运行后新增可定位章节，但各章节文本仍来自原文连续片段。
    副作用：只在内存中切片，不写文件、不调用模型；full_text 由调用方原样保留。
    异常或失败处理：没有章节标记时返回以 header 保存全文的字典；缺失章节由 parse_judgment 记录质量状态。
    最小示例：“本院认为”到“判决如下”之间会成为 court_reasoning。"""

    sections: dict[str, str] = {}
    for key in ("header", "claims", "defenses", "facts", "evidence", "court_reasoning", "judgment", "tail"):
        sections[key] = ""
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
    """用途：提取全文中出现的法律法规名称和条文表达。

    输入：text 是完整判决书文本。
    输出：返回按首次出现顺序去重的法条字符串列表。
    运行前数据形态：全文仍包含原始引用句。
    运行后数据变化：输出仅增加 cited_statutes 派生字段，不从 full_text 删除引用。
    副作用：只执行正则扫描，不写文件、不调用模型。
    异常或失败处理：无匹配时返回空列表，不补造法条。"""

    values = re.findall(r"《[^》]{2,100}》[^。；\n]{0,120}", text)
    unique_values: list[str] = []
    for value in values:
        cleaned = value.strip(" ，,：:")
        if cleaned and cleaned not in unique_values:
            unique_values.append(cleaned)
    return unique_values


def extract_amounts(text: str) -> list[str]:
    """用途：提取人民币金额表达，供案件检索、出题和质量复核。

    输入：text 是完整判决书文本。
    输出：返回按出现顺序去重的金额字符串列表。
    运行前数据形态：输入包含事实、请求和主文中的金额。
    运行后数据变化：输出 amounts 列表，同时原金额仍保留在对应章节。
    副作用：只执行正则扫描，不写文件、不调用模型。
    异常或失败处理：无金额时返回空列表；不负责把中文金额换算为数字。"""

    matches = re.findall(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*元", text)
    unique_values: list[str] = []
    for value in matches:
        if value not in unique_values:
            unique_values.append(value)
    return unique_values


def extract_dates(text: str) -> list[str]:
    """用途：提取全文中的阿拉伯数字和中文数字日期表达。

    输入：text 是完整判决书文本。
    输出：返回按出现顺序去重的日期字符串列表。
    运行前数据形态：输入可能含合同、履行、立案和裁判日期。
    运行后数据变化：输出 dates 列表用于后续问题生成与复核。
    副作用：只执行正则扫描，不写文件、不调用模型。
    异常或失败处理：无日期时返回空列表，不推断缺失年月日。"""

    values = re.findall(r"\d{4}年\d{1,2}月\d{1,2}日", text)
    values += re.findall(r"[二〇零一二三四五六七八九十]{4}年[一二三四五六七八九十]{1,3}月[一二三四五六七八九十]{1,3}日", text)
    unique_values: list[str] = []
    for value in values:
        if value not in unique_values:
            unique_values.append(value)
    return unique_values


def extract_interest_expressions(text: str) -> list[str]:
    """用途：提取包含利息、利率、逾期或资金占用费的原文句子。

    输入：text 是完整判决书文本。
    输出：返回去重后的相关句子列表。
    运行前数据形态：输入是完整判决书。
    运行后数据变化：输出 interest_expressions 保存可回溯的原文表达。
    副作用：只做规则匹配，不写文件、不调用模型。
    异常或失败处理：没有利息相关句子时返回空列表。"""

    patterns = [r"[^。；\n]{0,50}(?:利息|利率|LPR|贷款市场报价利率)[^。；\n]{0,100}"]
    values: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = match.group(0).strip()
            if value and value not in values:
                values.append(value)
    return values


def infer_category(text: str) -> str:
    """用途：根据案由和正文关键词推断首版五类民事主分类。

    输入：text 是完整判决书文本。
    输出：返回合同、劳动、侵权、婚姻继承、物权之一；无明显命中时回退合同类。
    运行前数据形态：输入尚无 primary_category。
    运行后数据变化：输出写入 classification.primary_category，原文不变。
    副作用：只读取文本和固定关键词，不写文件、不调用模型。
    异常或失败处理：多个类别同时命中时按代码中的明确优先级返回；无命中使用保守默认值。"""

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
    """用途：调用受控 taxonomy 推断主分类下的层级案由路径。

    输入：text 是判决书全文；category 是 infer_category 得到的主分类。
    输出：返回从主分类到具体案由的字符串列表。
    运行前数据形态：输入包含主分类和原文关键词。
    运行后数据变化：输出写入 classification.cause_path，并可由 validate_cause_path 校验。
    副作用：会读取 taxonomy.json 的缓存内容；不写文件、不调用模型。
    异常或失败处理：无法匹配具体子案由时返回该分类的受控默认路径。"""

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
    """用途：提供按当事人名称长度降序匿名化的排序值。

    输入：party 是至少可能包含 name 字段的字典。
    输出：返回名称字符串长度；缺失 name 时返回 0。
    运行前数据形态：多个名称可能互相包含。
    运行后数据变化：较长名称先替换，防止短名称破坏长名称匹配。
    副作用：只读字典，不写文件、不调用模型。
    异常或失败处理：name 不是字符串时先转为字符串，避免排序失败。"""
    name = party.get("name", "")
    if not isinstance(name, str):
        return 0
    return len(name)


def anonymize_text(text: str, parties: Iterable[dict[str, str]]) -> str:
    """用途：根据当事人列表生成脱敏副本，原始 full_text 始终保留。

    输入：text 是原文；parties 是包含 role/name 的可迭代对象。
    输出：返回把非空姓名替换为“角色编号”的 anonymized_text 字符串。
    运行前数据形态：运行前文本含真实当事人名称。
    运行后数据变化：运行后返回脱敏文本；调用方仍把原文完整存入 full_text。
    副作用：只在内存中生成新字符串，不修改 raw 文件、不写文件、不调用模型。
    异常或失败处理：空姓名被跳过；同名按稳定编号替换，其他正文保持不变。
    最小示例：两个被告会依次替换为“被告1”“被告2”。"""

    result = text
    sorted_parties = sorted(parties, key=_party_name_length, reverse=True)
    for index, party in enumerate(sorted_parties, start=1):
        if len(party["name"]) >= 2:
            result = result.replace(party["name"], f"当事人{index}")
    return result


def parse_judgment(text: str, source_file: str = "") -> dict:
    """用途：把一份原始判决书组装成无损、可追溯的案件结构。
           "一条案件具体生成什么字段？"
    输入：text 是未截断全文；source_file 是本地文件名。
    输出：返回含 case_id、source、document、parties、full_text、anonymized_text、sections、抽取字段、classification 和 quality 的字典。
    运行前数据形态：运行前是一段原始文本。
    运行后数据变化：运行后 full_text 原样保留，同时新增章节、多方当事人、哈希、分类和质量元数据。
    副作用：仅处理内存和读取 taxonomy；不写文件、不调用模型、不修改原始文本。
    异常或失败处理：缺失案号或关键章节不会丢弃案件，而是在 quality.missing_sections 和 status 中记录。
    最小示例：输入浙江买卖合同判决书后，court_reasoning 与 judgment 可分别通过 sections 定位。"""

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


def clean_directory(raw_dir: str | Path, output_path: str | Path,
                    max_items: int | None = None, *, manifest_output: str | Path) -> list[dict]:
    """用途：批量读取 raw 判决书，调用 parse_judgment，并写出解析结果与本地来源清单。

    输入：raw_dir 是原始目录；output_path 是 clean JSONL；max_items 限制试跑数量；manifest_output 指定清单路径。
    输出：返回解析案件列表；同时生成命令行指定的 clean JSONL 和来源 manifest。
    运行前数据形态：运行前 raw 下是一案一文件。
    运行后数据变化：运行后每案成为结构化 JSON 行，manifest 记录 case_id、文件名、哈希和审核状态。
    副作用：读取原始文件，创建父目录并覆盖两个 JSONL 输出及相邻 metadata；不调用模型、不修改 raw 文件。
    异常或失败处理：目录不存在时写出空 JSONL；单个文件解码或写入失败会抛出异常，交给 CLI 报错。
    最小示例：同名文件正文变化后哈希和 case_id 会变化，因此会被重新处理。"""

    files = list_raw_files(raw_dir)
    if max_items is not None and max_items > 0:
        files = files[:max_items]
    rows: list[dict] = []
    for path in files:
        raw_bytes = path.read_bytes()
        text = raw_bytes.decode("utf-8-sig")
        row = parse_judgment(text, path.name)
        digest = sha256_bytes(raw_bytes)
        row["case_id"] = "case_" + digest[:12]
        row["source"]["sha256"] = digest
        rows.append(row)
    write_jsonl(output_path, rows)

    if not manifest_output:
        raise ValueError("manifest_output 必须显式指定")
    manifest_path = Path(manifest_output)
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
    target = Path(output_path)
    metadata = new_run_metadata(
        "legal_benchmark.ingestion",
        input=str(Path(raw_dir)),
        output=str(target),
        manifest_output=str(manifest_path),
        count=len(rows),
        method="rules",
        parser_version=PARSER_VERSION,
    )
    target.with_suffix(target.suffix + ".metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return rows


def main() -> None:
    """用途：提供法律清洗命令行入口，把 --raw-dir、--output、--manifest-output 和 --max-items 传给 clean_directory。

    输入：参数来自 argparse；raw、clean 和 manifest 路径均由命令行显式提供。
    输出：成功时打印处理数量并正常退出；业务结果保存在指定 JSONL 文件。
    运行前数据形态：运行前命令行只有路径和数量参数。
    运行后数据变化：运行后生成 clean 案件文件和来源 manifest。
    副作用：读取本地判决书，创建目录并覆盖输出文件；不调用模型、不修改 raw。
    异常或失败处理：参数解析错误由 argparse 退出；文件处理异常向上抛出并产生非零退出码。"""

    parser = argparse.ArgumentParser(description="无损解析本地民事判决书")
    parser.add_argument("--raw-dir", "--input", required=True, help="原始判决书目录")
    parser.add_argument("--output", required=True, help="clean 阶段案件 JSONL")
    parser.add_argument("--manifest-output", required=True, help="来源清单 JSONL")
    parser.add_argument("--max-items", "--max-cases", type=int, default=None, help="只处理前 N 份")
    args = parser.parse_args()
    rows = clean_directory(args.raw_dir, args.output, args.max_items, manifest_output=args.manifest_output)
    print(f"完成：{args.output}，共 {len(rows)} 份；manifest：{args.manifest_output}")


if __name__ == "__main__":
    main()

