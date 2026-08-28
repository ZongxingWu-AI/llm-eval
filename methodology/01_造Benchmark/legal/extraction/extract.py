"""法律结构化信息提取模块。

    作用：
        读取 clean 案件
        基于 full_text 和全部 sections 建立全文案件事实地图
        保留旧版争议焦点、证据判断和法院结论字段
        给结果附 source_section 和 source_quote
        默认可用规则
        可选调用大模型
        大模型失败时保留规则结果



项目位置：法律真实案例评测线的 extraction 阶段。
输入：命令行指定的 clean 阶段案件 JSONL，其中包含完整原文和章节。
输出：命令行指定的 extract 阶段案件 JSONL，每案新增可回溯的 legal_extraction；同时写运行元数据。
上下游：上游是无损解析，下游是 generation.generate 的候选题生成。
副作用：覆盖指定 extract JSONL；默认只用规则，传入 --use-llm 时才调用 EXTRACTOR 模型。"""
import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core import llm_client
from core.data_io import read_jsonl, write_jsonl
from core.json_utils import parse_json_object
from core.prompt_loader import load_template, render
from core.run_metadata import new_run_metadata
from core.project_paths import LEGAL_PROMPT_ROOT as PROMPT_ROOT

EXTRACTOR_VERSION = "legal-extractor-v2"

FACT_MAP_GROUPS = (
    "key_facts",
    "party_relationships",
    "claims",
    "defenses",
    "evidence",
    "court_found_facts",
    "procedural_timeline",
    "applied_laws",
    "court_reasoning",
    "judgment_results",
)

_FACT_SECTION_NAMES = (
    "facts", "fact", "case_facts", "background", "case_background",
    "facts_summary", "source_material", "header",
)
_CLAIM_SECTION_NAMES = ("claims", "claim", "requests", "诉讼请求")
_DEFENSE_SECTION_NAMES = ("defenses", "defense", "arguments", "responses", "抗辩")
_EVIDENCE_SECTION_NAMES = ("evidence", "evidences", "evidence_materials", "证据")
_TIMELINE_SECTION_NAMES = (
    "procedural_timeline", "timeline", "procedure", "procedural_facts",
    "procedure_history", "tail",
)
_LAW_SECTION_NAMES = (
    "applied_laws", "laws", "cited_laws", "cited_statutes", "legal_basis",
)


class _QPSLimiter:
    """进程内线程安全的请求启动限流器。"""

    def __init__(self, qps: float):
        """初始化共享限流器；qps 表示本进程允许的请求启动速率。"""
        if qps <= 0:
            raise ValueError("qps 必须大于 0")
        self._interval = 1.0 / qps
        self._next_allowed = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        """等待到下一次允许发起请求的时间。"""
        with self._lock:
            now = time.monotonic()
            scheduled = max(now, self._next_allowed)
            self._next_allowed = scheduled + self._interval
        delay = scheduled - now
        if delay > 0:
            time.sleep(delay)


def _sentences(text: str) -> list[str]:
    """用途：把一个法律章节切成可逐句扫描且仍可回到原文定位的句子列表。
        "把章节拆成一句一句,为了让每条提取结果都能记录："
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


def _text(value) -> str:
    """把章节或模型字段安全地转换为可检索文本。"""

    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return "。".join(str(item).strip() for item in value if str(item).strip())
    if value is None:
        return ""
    return str(value).strip()


def _source_texts(case: dict) -> dict[str, str]:
    """返回可用于事实提取和来源校验的全文章节映射。

    优先使用 clean 阶段保留的全部 ``sections``。只有章节完全缺失时，才把
    ``full_text`` 作为一个可定位的 ``full_text`` 章节，避免无来源地猜测事实。
    """

    raw_sections = case.get("sections")
    sections: dict[str, str] = {}
    if isinstance(raw_sections, dict):
        for name, value in raw_sections.items():
            text = _text(value)
            if text:
                sections[str(name)] = text
    if not sections:
        full_text = _text(case.get("full_text"))
        if full_text:
            sections["full_text"] = full_text
    return sections


def _empty_fact_map() -> dict[str, list[dict]]:
    """创建固定键集合的空事实地图。"""

    return {group: [] for group in FACT_MAP_GROUPS}


def _fact_item(text: str, source_section: str, source_quote: str) -> dict | None:
    """创建严格三字段的事实地图条目。"""

    text = _text(text).strip()
    source_section = _text(source_section).strip()
    source_quote = _text(source_quote).strip()
    if not text or not source_section or not source_quote:
        return None
    return {
        "text": text,
        "source_section": source_section,
        "source_quote": source_quote,
    }


def _append_fact(fact_map: dict[str, list[dict]], group: str,
                 text: str, source_section: str, source_quote: str) -> None:
    """追加一个去重且可回查的事实地图条目。"""

    item = _fact_item(text, source_section, source_quote)
    if item is None or group not in fact_map:
        return
    if item not in fact_map[group]:
        fact_map[group].append(item)


def _sentences_from_sections(sections: dict[str, str], names) -> list[tuple[str, str]]:
    """按章节顺序返回指定章节中的 ``(章节名, 原文句子)``。"""

    wanted = set(names)
    result: list[tuple[str, str]] = []
    for section_name, section_text in sections.items():
        if section_name in wanted:
            result.extend((section_name, sentence) for sentence in _sentences(section_text))
    return result


def _all_sentences(sections: dict[str, str]) -> list[tuple[str, str]]:
    """按全文章节顺序返回所有非空句子。"""

    result: list[tuple[str, str]] = []
    for section_name, section_text in sections.items():
        result.extend((section_name, sentence) for sentence in _sentences(section_text))
    return result


def _contains_any(text: str, keywords) -> bool:
    """判断文本是否包含关键词集合中的任意一项。"""
    return any(keyword in text for keyword in keywords)


def _find_party_sentences(sections: dict[str, str], name: str, role: str) -> tuple[str, str] | None:
    """为当事人关系选择包含主体名称的原文连续句。"""

    for section_name, sentence in _all_sentences(sections):
        if name and name in sentence and (not role or role in sentence):
            return section_name, sentence
    for section_name, sentence in _all_sentences(sections):
        if name and name in sentence:
            return section_name, sentence
    return None


def _build_fact_map(case: dict, sections: dict[str, str]) -> dict[str, list[dict]]:
    """从全文章节和已解析的 parties 建立可回溯的十类事实地图。

    这是规则 fallback，不试图替代 LLM 的法律理解；它的职责是确保全文信息
    有稳定的、带原文定位的最低覆盖，尤其是在旧版 LLM 只返回三组字段时。
    """

    fact_map = _empty_fact_map()

    fact_sentences = _sentences_from_sections(sections, _FACT_SECTION_NAMES)
    if not fact_sentences:
        fact_sentences = [
            (section, sentence)
            for section, sentence in _all_sentences(sections)
            if section not in {"court_reasoning", "judgment"}
        ]
    for section, sentence in fact_sentences:
        _append_fact(fact_map, "key_facts", sentence, section, sentence)

    parties = case.get("parties", [])
    if isinstance(parties, list):
        for party in parties:
            if not isinstance(party, dict):
                continue
            role = _text(party.get("role"))
            name = _text(party.get("name"))
            located = _find_party_sentences(sections, name, role)
            if located:
                section, quote = located
                _append_fact(
                    fact_map, "party_relationships", f"{role}：{name}".strip("："), section, quote
                )
    if not fact_map["party_relationships"]:
        party_pattern = re.compile(r"(原告|被告|第三人|申请人|被申请人)\s*[:：]\s*([^，。；\n]+)")
        for section, sentence in _all_sentences(sections):
            for match in party_pattern.finditer(sentence):
                _append_fact(
                    fact_map, "party_relationships", f"{match.group(1)}：{match.group(2).strip()}",
                    section, sentence,
                )

    claim_sentences = _sentences_from_sections(sections, _CLAIM_SECTION_NAMES)
    if not claim_sentences:
        claim_sentences = [
            (section, sentence) for section, sentence in _all_sentences(sections)
            if _contains_any(sentence, ("诉讼请求", "请求", "要求", "诉请"))
        ]
    for section, sentence in claim_sentences:
        _append_fact(fact_map, "claims", sentence, section, sentence)

    defense_sentences = _sentences_from_sections(sections, _DEFENSE_SECTION_NAMES)
    if not defense_sentences:
        defense_sentences = [
            (section, sentence) for section, sentence in _all_sentences(sections)
            if _contains_any(sentence, ("辩称", "抗辩", "答辩", "不认可", "不同意"))
        ]
    for section, sentence in defense_sentences:
        _append_fact(fact_map, "defenses", sentence, section, sentence)

    evidence_sentences = _sentences_from_sections(sections, _EVIDENCE_SECTION_NAMES)
    if not evidence_sentences:
        evidence_sentences = [
            (section, sentence) for section, sentence in _all_sentences(sections)
            if _contains_any(sentence, ("证据", "提交", "出示", "证明", "举证"))
        ]
    for section, sentence in evidence_sentences:
        _append_fact(fact_map, "evidence", sentence, section, sentence)

    found_fact_sentences = [
        (section, sentence) for section, sentence in _sentences_from_sections(
            sections, ("facts", "fact", "case_facts", "facts_summary")
        )
    ]
    found_fact_sentences.extend(
        (section, sentence) for section, sentence in _sentences_from_sections(
            sections, ("court_reasoning",)
        ) if _contains_any(sentence, ("查明", "认定事实", "事实表明", "经审理查明"))
    )
    for section, sentence in found_fact_sentences:
        _append_fact(fact_map, "court_found_facts", sentence, section, sentence)

    timeline_sentences = _sentences_from_sections(sections, _TIMELINE_SECTION_NAMES)
    date_pattern = re.compile(r"(?:19|20)\d{2}[年./-]\d{1,2}[月./-]\d{1,2}日?|二[〇零一二三四五六七八九十百千万亿]+年")
    timeline_sentences.extend(
        (section, sentence) for section, sentence in _all_sentences(sections)
        if date_pattern.search(sentence) or _contains_any(
            sentence, ("起诉", "受理", "立案", "开庭", "送达", "上诉", "审理", "判决")
        )
    )
    for section, sentence in timeline_sentences:
        _append_fact(fact_map, "procedural_timeline", sentence, section, sentence)

    law_pattern = re.compile(r"《[^》]+》|第[一二三四五六七八九十百千万零〇\d]+条")
    law_sentences = _sentences_from_sections(sections, _LAW_SECTION_NAMES)
    law_sentences.extend(
        (section, sentence) for section, sentence in _all_sentences(sections)
        if law_pattern.search(sentence)
    )
    for section, sentence in law_sentences:
        _append_fact(fact_map, "applied_laws", sentence, section, sentence)

    for section, sentence in _sentences_from_sections(sections, ("court_reasoning",)):
        _append_fact(fact_map, "court_reasoning", sentence, section, sentence)
    for section, sentence in _sentences_from_sections(sections, ("judgment",)):
        _append_fact(fact_map, "judgment_results", sentence, section, sentence)

    return fact_map


def deterministic_extract(case: dict) -> dict:
    """用途：基于完整 ``sections/full_text`` 生成旧字段和全文事实地图。

             旧字段保持原有语义；``case_fact_map`` 是面向多维度出题的全文
             结构化 fallback。所有事实地图条目都严格保留原文来源定位。
    输入：case 是 ingestion 阶段产生且包含 sections 的案件字典。
    输出：返回旧版三组字段以及 ``case_fact_map`` 十个固定分组。
    运行前数据形态：运行前案件只有原文章节。
    运行后数据变化：运行后每条证据判断和结论都带 source_section 与 source_quote。
    副作用：只读取案件字典，不写文件、不调用模型。
    异常或失败处理：章节缺失时对应列表为空，不生成无来源结论。
    最小示例：判决主文中的一句会成为 conclusion，引用字段保存同一句原文。"""

    sections = _source_texts(case)
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
    return {
        "legal_issues": issues,
        "evidence_findings": evidence_findings,
        "conclusions": conclusions,
        "case_fact_map": _build_fact_map(case, sections),
    }


def _valid_grounded_items(items, sections: dict) -> list[dict]:
    """用途：过滤无法通过章节名和原文短引定位的模型提取项。

           "怎么防止大模型胡编来源？"

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


def _valid_fact_items(items, sections: dict) -> list[dict]:
    """校验并规范模型返回的新事实地图条目。

    新契约只接受 ``text/source_section/source_quote`` 三个字段；为兼容旧版
    提取 Prompt，也允许模型把旧字段中的 ``conclusion`` 作为 text 来源，
    但输出统一规范为三字段。
    """

    if not isinstance(items, list):
        return []
    valid: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        section = _text(item.get("source_section"))
        quote = _text(item.get("source_quote"))
        text = _text(item.get("text") or item.get("conclusion") or item.get("fact"))
        if section not in sections or not quote or quote not in sections[section]:
            continue
        normalized = _fact_item(text, section, quote)
        if normalized is not None and normalized not in valid:
            valid.append(normalized)
    return valid


def _normalise_issues(values) -> list[str]:
    """规范旧版 legal_issues 字符串数组。"""

    if not isinstance(values, list):
        return []
    return [issue for issue in (_text(value).strip() for value in values) if issue]


def _candidate_fact_map(candidate: dict, sections: dict) -> tuple[dict[str, list[dict]], list[str], bool]:
    """提取候选事实地图；缺失字段由规则 fallback 补齐。"""

    candidate_map = candidate.get("case_fact_map")
    if not isinstance(candidate_map, dict):
        candidate_map = candidate
    fact_map = _empty_fact_map()
    errors: list[str] = []
    used = False
    for group in FACT_MAP_GROUPS:
        if group not in candidate_map:
            continue
        used = True
        raw_items = candidate_map.get(group)
        if not isinstance(raw_items, list):
            errors.append(f"模型事实地图字段 {group} 不是数组，已保留规则 fallback")
            continue
        valid = _valid_fact_items(raw_items, sections)
        if len(valid) != len(raw_items):
            errors.append(f"模型事实地图字段 {group} 存在无法回查的引用，已保留规则 fallback")
            continue
        fact_map[group] = valid
    return fact_map, errors, used


def extract_case(case: dict, client=None, model: str = "", before_model_call=None) -> dict:
    """用途：为单个 clean 案件生成 legal_extraction，并在启用客户端时融合有来源的大模型结果。

       "规则兜底:
        extract_case()
            ↓
        先调用 deterministic_extract()
            ↓
        先得到规则结果
             ↓
        如果没有 client：
            直接使用规则结果
             ↓
        如果有 client：
            再尝试调用大模型
             ↓
        大模型成功且结果可定位：
            使用 llm_grounded 结果
             ↓
        大模型失败：
            保留前面已经得到的规则结果

    输入：case 是 clean 案件；client/model 为空时只走规则路径；before_model_call 可在每次模型请求前限流。
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
        prompt = render(template, {
            "case_sections": json.dumps({
                "full_text": _text(case.get("full_text")),
                "sections": case.get("sections", {}),
            }, ensure_ascii=False),
            "case_full_text": _text(case.get("full_text")),
        })
        try:
            raw = llm_client.call_model(
                client, model, prompt, 0, 8192, before_attempt=before_model_call
            )[0]
            candidate = parse_json_object(raw)
            sections = _source_texts(case)
            candidate_conclusions = candidate.get("conclusions")
            candidate_evidence = candidate.get("evidence_findings")
            legacy_present = any(
                field in candidate for field in ("legal_issues", "evidence_findings", "conclusions")
            )
            legacy_valid = True
            legacy_values = {
                "legal_issues": extracted["legal_issues"],
                "evidence_findings": extracted["evidence_findings"],
                "conclusions": extracted["conclusions"],
            }
            if "legal_issues" in candidate:
                if not isinstance(candidate.get("legal_issues"), list):
                    legacy_valid = False
                else:
                    legacy_values["legal_issues"] = _normalise_issues(candidate.get("legal_issues"))
            if "conclusions" in candidate:
                if not isinstance(candidate_conclusions, list):
                    legacy_valid = False
                else:
                    llm_conclusions = _valid_grounded_items(candidate_conclusions, sections)
                    if len(llm_conclusions) != len(candidate_conclusions):
                        legacy_valid = False
                    else:
                        legacy_values["conclusions"] = llm_conclusions
            if "evidence_findings" in candidate:
                if not isinstance(candidate_evidence, list):
                    legacy_valid = False
                else:
                    llm_evidence = _valid_grounded_items(candidate_evidence, sections)
                    if len(llm_evidence) != len(candidate_evidence):
                        legacy_valid = False
                    else:
                        legacy_values["evidence_findings"] = llm_evidence

            candidate_map, map_errors, map_present = _candidate_fact_map(candidate, sections)
            errors.extend(map_errors)
            if legacy_present and not legacy_valid:
                errors.append("模型旧版字段引用无法在原章节定位，已回退规则提取")
            else:
                extracted = {
                    **extracted,
                    **legacy_values,
                    "case_fact_map": {
                        group: candidate_map[group] if group in candidate_map and group in candidate.get("case_fact_map", candidate) and not any(
                            error.startswith(f"模型事实地图字段 {group}") for error in map_errors
                        ) else extracted["case_fact_map"][group]
                        for group in FACT_MAP_GROUPS
                    },
                }
                if legacy_present or map_present:
                    method = "llm_grounded"
        except Exception as exc:
            errors.append(f"模型提取失败，已回退规则提取：{exc}")
    result = dict(case)
    result["legal_extraction"] = extracted
    result.setdefault("classification", {})["legal_issues"] = extracted["legal_issues"]
    result.setdefault("quality", {})["extraction"] = {
        "version": EXTRACTOR_VERSION, "method": method, "status": "needs_review", "errors": errors
    }
    return result


def _summarize_methods(results: list[dict]) -> tuple[str, dict[str, int]]:
    """根据每条案件的实际提取结果汇总批次方法。

    返回值中的 ``method`` 不依据 ``--use-llm`` 推断，而是读取每条结果的
    ``quality.extraction.method``。这样即使模型调用失败并回退规则，批次元数据
    也会如实记录为 ``rules`` 或 ``mixed``。
    """

    method_counts = {"rules": 0, "llm_grounded": 0}
    for result in results:
        method = result.get("quality", {}).get("extraction", {}).get("method")
        if method in method_counts:
            method_counts[method] += 1

    used_methods = [method for method, count in method_counts.items() if count]
    if not used_methods:
        batch_method = "none"
    elif len(used_methods) == 1:
        batch_method = used_methods[0]
    else:
        batch_method = "mixed"
    return batch_method, method_counts


def _fallback_result(case: dict, error: Exception) -> dict:
    """把未预期的单案异常转换为规则降级结果，避免中断整批处理。"""
    try:
        extracted = deterministic_extract(case)
        errors = [f"单案处理失败，已回退规则提取：{error}"]
    except Exception as fallback_error:
        extracted = {
            "legal_issues": [],
            "evidence_findings": [],
            "conclusions": [],
            "case_fact_map": _empty_fact_map(),
        }
        errors = [
            f"单案处理失败：{error}",
            f"规则降级也失败：{fallback_error}",
        ]
    result = dict(case)
    result["legal_extraction"] = extracted
    result["classification"] = dict(case.get("classification", {}))
    result["classification"]["legal_issues"] = extracted["legal_issues"]
    result["quality"] = dict(case.get("quality", {}))
    result["quality"]["extraction"] = {
        "version": EXTRACTOR_VERSION,
        "method": "rules",
        "status": "needs_review",
        "errors": errors,
    }
    return result


def _extract_one(case: dict, client, model: str, limiter: _QPSLimiter | None) -> dict:
    """在线程池中处理单案；意外异常也转换成规则降级结果。"""
    try:
        before_model_call = limiter.wait if limiter is not None else None
        return extract_case(case, client, model, before_model_call=before_model_call)
    except Exception as exc:
        return _fallback_result(case, exc)


def run(input_path: str | Path, output_path: str | Path,
        max_items: int | None = None, use_llm: bool = False,
        workers: int = 4, qps: float = 3) -> list[dict]:
    """用途：批量读取 clean JSONL，执行结构化法律提取并写入 extract JSONL 和运行元数据。

    输入：input_path、output_path、max_items 控制数据；use_llm 决定是否配置 EXTRACTOR 模型；workers 和 qps 控制模型并发与限流。
    输出：返回结构化案件列表，并写命令行指定的 extract JSONL 及相邻 metadata.json。
    运行前数据形态：运行前每行是 clean 案件。
    运行后数据变化：运行后每行新增 legal_extraction，元数据记录数量、模型、并发和限流参数。
    副作用：读取 JSONL、创建目录并覆盖输出；仅 use_llm=True 时读取环境变量并调用模型。
    异常或失败处理：模型角色未配置或单案失败时按现有异常策略处理；max_items 只截取本次试跑。"""

    if workers <= 0:
        raise ValueError("workers 必须大于 0")
    if qps <= 0:
        raise ValueError("qps 必须大于 0")

    rows = read_jsonl(input_path)
    if max_items is not None and max_items > 0:
        rows = rows[:max_items]
    client = None
    model = ""
    if use_llm:
        llm_client.load_env()
        base, key, model = llm_client.read_role("EXTRACTOR", "deepseek-v4-flash")
        client = llm_client.build_client(base, key)
    limiter = _QPSLimiter(qps) if use_llm else None
    if use_llm and workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_extract_one, row, client, model, limiter) for row in rows]
            results = [future.result() for future in futures]
    else:
        results = [_extract_one(row, client, model, limiter) for row in rows]
    write_jsonl(output_path, results)
    target = Path(output_path)
    batch_method, method_counts = _summarize_methods(results)
    metadata = new_run_metadata("legal_benchmark.extraction", input=str(input_path), output=str(output_path),
                                count=len(results), method=batch_method, method_counts=method_counts,
                                model=model, workers=workers, qps=qps)
    target.with_suffix(target.suffix + ".metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def main() -> None:
    """用途：提供结构化提取 CLI，把输入、输出、试跑数量和 --use-llm 传给 run。

    输入：参数来自 argparse；clean 输入和 extract 输出路径均显式提供。
    输出：成功打印案件数；失败打印错误并以状态码 1 退出。
    运行前数据形态：运行前是命令行参数。
    运行后数据变化：运行后生成可供候选题生成使用的 extract 案件 JSONL。
    副作用：会覆盖指定 extract JSONL 和相邻元数据；只有 --use-llm 时调用模型。
    异常或失败处理：参数错误由 argparse 处理；run 抛出的异常转换为非零退出。"""

    parser = argparse.ArgumentParser(description="提取带原文定位的法律结构化信息")
    parser.add_argument("--input", required=True, help="clean 阶段案件 JSONL")
    parser.add_argument("--output", required=True, help="extract 阶段案件 JSONL")
    parser.add_argument("--max-items", "--max-cases", type=int, default=None, help="只处理前 N 案")
    parser.add_argument("--use-llm", action="store_true", help="使用模型提取；不传则使用可重复的规则提取")
    parser.add_argument("--workers", type=int, default=4, help="LLM 最大并发工作线程数，默认 4")
    parser.add_argument("--qps", type=float, default=3, help="LLM 请求启动速率上限，默认每秒 3 次")
    args = parser.parse_args()
    try:
        rows = run(args.input, args.output, args.max_items, args.use_llm, args.workers, args.qps)
        print(f"完成：{args.output}，共 {len(rows)} 案")
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
