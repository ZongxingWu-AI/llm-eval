"""法律结构化信息提取模块。

    作用：
        读取 clean 案件
        基于唯一的脱敏全文建立全文案件事实地图
        统一生成当前 canonical case_fact_map
        给结果附 source_quote 和本地生成的 source_quote_sha256
        默认可用规则
        可选调用大模型
        大模型失败时保留规则结果



项目位置：法律真实案例评测线的 extraction 阶段。
输入：命令行指定的 clean 阶段案件 JSONL，其中包含唯一脱敏全文 external_text。
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
import hashlib

from core import llm_client
from core.data_io import read_jsonl, write_jsonl
from core.json_utils import parse_json_object
from core.prompt_loader import load_template, render
from core.run_metadata import new_run_metadata
from core.project_paths import LEGAL_PROMPT_ROOT as PROMPT_ROOT

EXTRACTOR_VERSION = "legal-extractor-v3"

FACT_MAP_GROUPS = (
    "key_facts",
    "party_relationships",
    "claims",
    "defenses",
    "disputed_issues",
    "evidence",
    "court_found_facts",
    "procedural_timeline",
    "applied_laws",
    "court_reasoning",
    "judgment_results",
)


# OpenAI 兼容结构化输出契约：模型只能返回完整事实地图，引用哈希由本地生成。
_FACT_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "minLength": 1},
        "source_quote": {"type": "string", "minLength": 1},
    },
    "required": ["text", "source_quote"],
    "additionalProperties": False,
}
LEGAL_EXTRACTION_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "legal_case_fact_map",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "case_fact_map": {
                    "type": "object",
                    "properties": {group: {"type": "array", "items": _FACT_ITEM_SCHEMA} for group in FACT_MAP_GROUPS},
                    "required": list(FACT_MAP_GROUPS),
                    "additionalProperties": False,
                },
            },
            "required": ["case_fact_map"],
            "additionalProperties": False,
        },
    },
}

_FACT_SECTION_NAMES = (
    "facts", "fact", "case_facts", "background", "case_background", "header",
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

# 规则 fallback 只在内存中对 external_text 做粗粒度扫描；结果不写回案件接口。
_EXTERNAL_SECTION_MARKERS = {
    "claims": ("诉讼请求", "请求事项"),
    "defenses": ("被告辩称", "被告答辩", "答辩意见", "未作答辩"),
    "facts": ("经审理查明", "审理查明", "本院查明"),
    "court_reasoning": ("本院认为", "法院认为"),
    "judgment": ("判决如下", "裁判主文", "判决主文"),
}


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


def _external_marker_positions(text: str) -> list[tuple[int, str]]:
    """在脱敏全文中定位规则 fallback 使用的临时扫描边界。"""
    positions: list[tuple[int, str]] = []
    for section, markers in _EXTERNAL_SECTION_MARKERS.items():
        matches = [re.search(re.escape(marker), text) for marker in markers]
        matches = [match for match in matches if match]
        if matches:
            positions.append((min(match.start() for match in matches), section))
    return sorted(positions)


def _source_groups(external_text: str) -> dict[str, str]:
    """从唯一的脱敏全文建立规则 fallback 的临时扫描视图。

    该视图只存在于当前函数调用的内存中，不读取或保存 clean 阶段的章节字段，
    也不改变 LLM 引用校验：模型引用仍必须直接出现在完整 external_text 中。
    """
    if not external_text:
        return {}
    groups = {key: "" for key in (
        "header", "claims", "defenses", "facts", "evidence",
        "court_reasoning", "judgment", "tail",
    )}
    positions = _external_marker_positions(external_text)
    if not positions:
        groups["header"] = external_text
        return groups
    groups["header"] = external_text[:positions[0][0]]
    for index, (start_pos, section) in enumerate(positions):
        end_pos = positions[index + 1][0] if index + 1 < len(positions) else len(external_text)
        groups[section] = external_text[start_pos:end_pos]
    facts = groups["facts"]
    evidence_match = re.search(r"(?:以上事实|上述事实).{0,20}(?:证据|证明)", facts)
    if evidence_match:
        groups["evidence"] = facts[evidence_match.start():]
        groups["facts"] = facts[:evidence_match.start()]
    judgment = groups["judgment"]
    tail_match = re.search(r"(?:如不服本判决|审判长|审判员|书记员|本件与原本核对无异)", judgment)
    if tail_match:
        groups["tail"] = judgment[tail_match.start():]
        groups["judgment"] = judgment[:tail_match.start()]
    return {str(name): _text(value) for name, value in groups.items() if _text(value)}


def _empty_fact_map() -> dict[str, list[dict]]:
    """创建固定键集合的空事实地图。"""

    return {group: [] for group in FACT_MAP_GROUPS}


def _fact_item(text: str, source_quote: str) -> dict | None:
    """创建事实地图条目；哈希只由本地程序计算，不携带章节标签。"""

    text = _text(text).strip()
    source_quote = _text(source_quote).strip()
    if not text or not source_quote:
        return None
    return {
        "text": text,
        "source_quote": source_quote,
        "source_quote_sha256": hashlib.sha256(source_quote.encode("utf-8")).hexdigest(),
    }

def _append_fact(fact_map: dict[str, list[dict]], group: str,
                 text: str, source_quote: str) -> None:
    """追加一个去重且可回查的事实地图条目。"""

    item = _fact_item(text, source_quote)
    if item is None or group not in fact_map:
        return
    if item not in fact_map[group]:
        fact_map[group].append(item)


def _sentences_from_groups(groups: dict[str, str], names) -> list[tuple[str, str]]:
    """按章节顺序返回指定章节中的 ``(章节名, 原文句子)``。"""

    wanted = set(names)
    result: list[tuple[str, str]] = []
    for section_name, section_text in groups.items():
        if section_name in wanted:
            result.extend((section_name, sentence) for sentence in _sentences(section_text))
    return result


def _all_sentences(groups: dict[str, str]) -> list[tuple[str, str]]:
    """按全文章节顺序返回所有非空句子。"""

    result: list[tuple[str, str]] = []
    for section_name, section_text in groups.items():
        result.extend((section_name, sentence) for sentence in _sentences(section_text))
    return result


def _contains_any(text: str, keywords) -> bool:
    """判断文本是否包含关键词集合中的任意一项。"""
    return any(keyword in text for keyword in keywords)


def _find_party_sentences(groups: dict[str, str], name: str, role: str) -> tuple[str, str] | None:
    """为当事人关系选择包含主体名称的原文连续句。"""

    for section_name, sentence in _all_sentences(groups):
        if name and name in sentence and (not role or role in sentence):
            return section_name, sentence
    for section_name, sentence in _all_sentences(groups):
        if name and name in sentence:
            return section_name, sentence
    return None


def _build_fact_map(case: dict, groups: dict[str, str]) -> dict[str, list[dict]]:
    """从全文章节和已解析的 parties 建立可回溯的十类事实地图。

    这是规则 fallback，不试图替代 LLM 的法律理解；它的职责是确保全文信息
    有稳定的、带原文定位的最低覆盖，作为模型抽取失败时的规则排查结果。
    """

    fact_map = _empty_fact_map()

    fact_sentences = _sentences_from_groups(groups, _FACT_SECTION_NAMES)
    if not fact_sentences:
        fact_sentences = [
            (section, sentence)
            for section, sentence in _all_sentences(groups)
            if section not in {"court_reasoning", "judgment"}
        ]
    for section, sentence in fact_sentences:
        _append_fact(fact_map, "key_facts", sentence, sentence)

    parties = case.get("parties", [])
    if isinstance(parties, list):
        for party in parties:
            if not isinstance(party, dict):
                continue
            role = _text(party.get("role"))
            name = _text(party.get("name"))
            located = _find_party_sentences(groups, name, role)
            if located:
                section, quote = located
                _append_fact(
                    fact_map, "party_relationships", f"{role}：{name}".strip("："), quote
                )
    if not fact_map["party_relationships"]:
        party_pattern = re.compile(r"(原告|被告|第三人|申请人|被申请人)\s*[:：]\s*([^，。；\n]+)")
        for section, sentence in _all_sentences(groups):
            for match in party_pattern.finditer(sentence):
                _append_fact(
                    fact_map, "party_relationships", f"{match.group(1)}：{match.group(2).strip()}",
                    sentence,
                )

    claim_sentences = _sentences_from_groups(groups, _CLAIM_SECTION_NAMES)
    if not claim_sentences:
        claim_sentences = [
            (section, sentence) for section, sentence in _all_sentences(groups)
            if _contains_any(sentence, ("诉讼请求", "请求", "要求", "诉请"))
        ]
    for section, sentence in claim_sentences:
        _append_fact(fact_map, "claims", sentence, sentence)

    defense_sentences = _sentences_from_groups(groups, _DEFENSE_SECTION_NAMES)
    if not defense_sentences:
        defense_sentences = [
            (section, sentence) for section, sentence in _all_sentences(groups)
            if _contains_any(sentence, ("辩称", "抗辩", "答辩", "不认可", "不同意"))
        ]
    for section, sentence in defense_sentences:
        _append_fact(fact_map, "defenses", sentence, sentence)

    issue_sentences = _sentences_from_groups(groups, ("court_reasoning",))
    issue_sentences = [
        (section, sentence) for section, sentence in issue_sentences
        if sentence.startswith("关于") or _contains_any(sentence, ("争议焦点", "争议在于", "焦点是"))
    ]
    for section, sentence in issue_sentences:
        _append_fact(fact_map, "disputed_issues", sentence, sentence)

    evidence_sentences = _sentences_from_groups(groups, _EVIDENCE_SECTION_NAMES)
    if not evidence_sentences:
        evidence_sentences = [
            (section, sentence) for section, sentence in _all_sentences(groups)
            if _contains_any(sentence, ("证据", "提交", "出示", "证明", "举证"))
        ]
    for section, sentence in evidence_sentences:
        _append_fact(fact_map, "evidence", sentence, sentence)

    found_fact_sentences = [
        (section, sentence) for section, sentence in _sentences_from_groups(
            groups, ("facts", "fact", "case_facts")
        )
    ]
    found_fact_sentences.extend(
        (section, sentence) for section, sentence in _sentences_from_groups(
            groups, ("court_reasoning",)
        ) if _contains_any(sentence, ("查明", "认定事实", "事实表明", "经审理查明"))
    )
    for section, sentence in found_fact_sentences:
        _append_fact(fact_map, "court_found_facts", sentence, sentence)

    timeline_sentences = _sentences_from_groups(groups, _TIMELINE_SECTION_NAMES)
    date_pattern = re.compile(r"(?:19|20)\d{2}[年./-]\d{1,2}[月./-]\d{1,2}日?|二[〇零一二三四五六七八九十百千万亿]+年")
    timeline_sentences.extend(
        (section, sentence) for section, sentence in _all_sentences(groups)
        if date_pattern.search(sentence) or _contains_any(
            sentence, ("起诉", "受理", "立案", "开庭", "送达", "上诉", "审理", "判决")
        )
    )
    for section, sentence in timeline_sentences:
        _append_fact(fact_map, "procedural_timeline", sentence, sentence)

    law_pattern = re.compile(r"《[^》]+》|第[一二三四五六七八九十百千万零〇\d]+条")
    law_sentences = _sentences_from_groups(groups, _LAW_SECTION_NAMES)
    law_sentences.extend(
        (section, sentence) for section, sentence in _all_sentences(groups)
        if law_pattern.search(sentence)
    )
    for section, sentence in law_sentences:
        _append_fact(fact_map, "applied_laws", sentence, sentence)

    for section, sentence in _sentences_from_groups(groups, ("court_reasoning",)):
        _append_fact(fact_map, "court_reasoning", sentence, sentence)
    judgment_sentences = _sentences_from_groups(groups, ("judgment",))
    if not judgment_sentences:
        # 简化输入有时没有可识别的“判决如下”章节标记；此时仍从全文
        # 提取明确的裁判主文句，避免规则排查结果漏掉结论。
        judgment_sentences = [
            (section, sentence)
            for section, sentence in _all_sentences(groups)
            if _contains_any(sentence, ("判决", "裁定", "驳回诉讼请求", "支持诉讼请求"))
        ]
    for section, sentence in judgment_sentences:
        _append_fact(fact_map, "judgment_results", sentence, sentence)

    return fact_map


def deterministic_extract(case: dict) -> dict:
    """基于完整脱敏章节生成 canonical 事实地图。

    规则结果仅作为排查用 fallback，不能被视为专家确认结果。
    """
    external_text = _text(case.get("external_text"))
    source_groups = _source_groups(external_text)
    return {"case_fact_map": _build_fact_map(case, source_groups)}


def _valid_fact_items(items, external_text: str) -> tuple[list[dict], list[str]]:
    """严格校验模型条目，并由程序生成引用哈希。"""

    if not isinstance(items, list):
        return [], ["字段不是数组"]
    valid: list[dict] = []
    errors: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"第 {index} 项不是对象")
            continue
        allowed = {"text", "source_quote"}
        extra = set(item) - allowed
        if extra:
            errors.append(f"第 {index} 项包含未定义字段")
            continue
        quote = _text(item.get("source_quote"))
        text = _text(item.get("text"))
        if not text or not quote:
            errors.append(f"第 {index} 项缺少 text/source_quote")
            continue
        if quote not in external_text:
            errors.append(f"第 {index} 项 source_quote 无法在脱敏全文中逐字回查")
            continue
        normalized = _fact_item(text, quote)
        if normalized is not None and normalized not in valid:
            valid.append(normalized)
    return valid, errors

def _candidate_fact_map(candidate: dict, external_text: str) -> tuple[dict[str, list[dict]], list[str], bool]:
    """严格校验完整 canonical case_fact_map，不做部分字段或规则混合。"""
    errors: list[str] = []
    if not isinstance(candidate, dict):
        return _empty_fact_map(), ["模型输出不是对象"], False
    if set(candidate) != {"case_fact_map"}:
        extras = set(candidate) - {"case_fact_map"}
        if extras:
            errors.append("模型顶层包含未定义字段")
    candidate_map = candidate.get("case_fact_map")
    if not isinstance(candidate_map, dict):
        errors.append("模型输出缺少 case_fact_map 对象")
        return _empty_fact_map(), errors, False
    missing = [group for group in FACT_MAP_GROUPS if group not in candidate_map]
    extras = [group for group in candidate_map if group not in FACT_MAP_GROUPS]
    if missing:
        errors.append("模型事实地图缺少字段：" + ", ".join(missing))
    if extras:
        errors.append("模型事实地图包含未定义字段")
    if errors:
        return _empty_fact_map(), errors, False
    fact_map = _empty_fact_map()
    for group in FACT_MAP_GROUPS:
        valid, item_errors = _valid_fact_items(candidate_map[group], external_text)
        if item_errors:
            errors.extend([f"{group}：{message}" for message in item_errors])
        if len(valid) != len(candidate_map[group]):
            errors.append(f"模型事实地图字段 {group} 存在重复或无效条目")
        fact_map[group] = valid
    return fact_map, errors, True

def extract_case(case: dict, client=None, model: str = "", before_model_call=None) -> dict:
    """为单个案件生成 canonical 事实地图和可信状态。"""
    fallback = deterministic_extract(case)
    extracted = fallback
    method = "rules_fallback"
    review_status = "needs_review"
    errors: list[str] = []
    if client is not None:
        template = load_template("legal_extraction_prompt.md", PROMPT_ROOT)
        external_text = _text(case.get("external_text"))
        prompt = render(template, {"external_text": external_text})
        try:
            raw = llm_client.call_model(
                client, model, prompt, 0, 8192,
                before_attempt=before_model_call,
                response_format=LEGAL_EXTRACTION_RESPONSE_FORMAT,
            )[0]
            candidate = parse_json_object(raw)
            # 引用校验的唯一权威来源是完整脱敏全文；不拼接其他案件字段或原始文本。
            candidate_map, map_errors, complete = _candidate_fact_map(candidate, external_text)
            if not complete or map_errors:
                errors.extend(map_errors or ["模型事实地图未通过完整性校验"])
            else:
                extracted = {"case_fact_map": candidate_map}
                method = "llm_grounded"
                review_status = "ready_for_generation"
        except Exception as exc:
            errors.append(f"模型提取失败，已保留规则排查结果：{exc}")
    else:
        errors.append("未启用 LLM 抽取，当前事实地图仅为规则排查结果")
    result = dict(case)
    result["legal_extraction"] = extracted
    result["quality"] = dict(case.get("quality", {}))
    result["quality"]["extraction"] = {
        "version": EXTRACTOR_VERSION,
        "method": method,
        "status": review_status,
        "review_status": review_status,
        "errors": errors,
    }
    return result

def _extract_one(case: dict, client=None, model: str = "", limiter=None) -> dict:
    """执行单案抽取，并把意外异常转换为 needs_review 结果。

    该包装器由批量串行/并发路径共用，确保单个案件失败不会中断整个批次，
    同时通过共享 limiter 控制每个模型请求的启动时间。
    """
    try:
        before_model_call = limiter.wait if limiter is not None else None
        return extract_case(
            case,
            client,
            model,
            before_model_call=before_model_call,
        )
    except Exception as exc:
        return _fallback_result(case, exc)
def _summarize_methods(results: list[dict]) -> tuple[str, dict[str, int]]:
    """汇总 llm_grounded 与 rules_fallback 的案件数。"""
    method_counts = {"rules_fallback": 0, "llm_grounded": 0}
    for result in results:
        method = result.get("quality", {}).get("extraction", {}).get("method")
        if method in method_counts:
            method_counts[method] += 1
    used_methods = [method for method, count in method_counts.items() if count]
    return ("none" if not used_methods else used_methods[0] if len(used_methods) == 1 else "mixed", method_counts)


def _fallback_result(case: dict, error: Exception) -> dict:
    """把单案异常转换为需要审核的规则排查结果。"""
    try:
        extracted = deterministic_extract(case)
        errors = [f"单案处理失败，已保留规则排查结果：{error}"]
    except Exception as fallback_error:
        extracted = {"case_fact_map": _empty_fact_map()}
        errors = [f"单案处理失败：{error}", f"规则排查也失败：{fallback_error}"]
    result = dict(case)
    result["legal_extraction"] = extracted
    result["quality"] = dict(case.get("quality", {}))
    result["quality"]["extraction"] = {
        "version": EXTRACTOR_VERSION,
        "method": "rules_fallback",
        "status": "needs_review",
        "review_status": "needs_review",
        "errors": errors,
    }
    return result


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
