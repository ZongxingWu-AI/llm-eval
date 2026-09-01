"""法律 Benchmark 的统一多维度候选题生成引擎。

本模块只负责 02「构建题集」阶段的候选题生成：

* 用 ``dimension_id`` 路由到对应 Prompt；
* 将唯一的脱敏全文、legal_extraction、事实地图和精确引用材料交给出题模型；
* 对模型返回的题目做轻量结构和原文证据校验；
* 单个维度或单个案件失败时继续处理其他请求。

题目发布后的 ``context`` 与 ``question`` 是 03 模型作答阶段的唯一题面材料，
因此生成模型必须把被测模型需要的材料放进 ``context``，而不是要求被测模型
读取本 Prompt 或依赖未提供的“上文”。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
import threading
import time
from collections import Counter, defaultdict
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from core import llm_client
from core.data_io import read_jsonl, write_jsonl
from core.json_utils import parse_json_value
from core.prompt_loader import load_template, render
from core.run_metadata import new_run_metadata

# 02 的 Prompt 不应继续引用 01 的旧 legal_generation_prompt。
PROMPT_ROOT = Path(__file__).resolve().parents[1] / "prompts"
_PROJECT_ROOT = Path(__file__).resolve().parents[4]

_taxonomy = importlib.import_module("methodology.01_造Benchmark.legal.taxonomy")
load_taxonomy = _taxonomy.load_taxonomy
_config = importlib.import_module("methodology.02_构建题集.legal.config")
_config_load_dimension_catalog = _config.load_dimension_catalog
_config_load_question_format_catalog = _config.load_question_format_catalog
_config_get_question_format = _config.get_question_format

_CONTEXT_TYPES = {"source_excerpt", "full_document", "self_contained", "scenario"}
OUTCOME_MARKERS = ("判决如下", "裁判如下", "判决主文", "裁判主文", "本院判决", "裁定如下", "裁定主文", "判决：", "裁判：")

_FACT_MAP_FIELDS = (
    "key_facts", "party_relationships", "claims", "defenses", "disputed_issues",
    "evidence", "court_found_facts", "procedural_timeline", "applied_laws",
    "court_reasoning", "judgment_results",
)

REQUIRED_FIELDS = (
    "task_type", "answer_type",
    "scoring_method", "difficulty", "risk_level", "question", "reference_answer",
    "rubric", "source_evidence",
)
NEW_CONTRACT_FIELDS = (
    "dimension_id", "task_type", "context_type", "context", "question",
    "reference_answer", "rubric", "source_evidence",
)


class _QPSLimiter:
    """进程内线程安全的请求启动速率限流器。"""

    def __init__(self, qps: float):
        """按指定 QPS 初始化所有生成线程共享的限流状态。"""
        if qps <= 0:
            raise ValueError("qps must be positive")
        self._interval = 1.0 / qps
        self._next_allowed = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        """等待共享限流器允许下一次模型请求启动。"""
        with self._lock:
            now = time.monotonic()
            scheduled = max(now, self._next_allowed)
            self._next_allowed = scheduled + self._interval
        delay = scheduled - now
        if delay > 0:
            time.sleep(delay)


def _normalise_catalog_document(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """把配置 loader 的文档形态转换成 ``dimension_id -> config`` 索引。

    config loader 的正式返回值是 ``{"dimensions": [...], "blueprint": ...}``；
    这里保留一个索引形态，兼容早期 generation 测试和旧调用方。
    """

    dimensions = document.get("dimensions") if isinstance(document, Mapping) else None
    if isinstance(dimensions, list):
        return {
            str(item["dimension_id"]): dict(item)
            for item in dimensions
            if isinstance(item, Mapping) and item.get("dimension_id")
        }
    if isinstance(document, Mapping):
        return {
            str(key): dict(value)
            for key, value in document.items()
            if isinstance(value, Mapping) and key not in {"blueprint", "dimensions"}
        }
    raise ValueError("法律维度目录必须包含 dimensions 数组")


def _load_catalog_document(path: str | Path | None = None) -> Mapping[str, Any]:
    """读取正式目录；对旧的、仅含少量字段的测试目录保留兼容回退。"""

    if path is None:
        return _config_load_dimension_catalog()
    try:
        return _config_load_dimension_catalog(path)
    except (FileNotFoundError, ValueError):
        # 旧测试夹具只有两维，且没有 target_count 等正式字段。
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("dimensions"), list):
            raise
        return raw


def load_dimension_catalog(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """加载维度目录并按 ``dimension_id`` 建立索引。"""

    return _normalise_catalog_document(_load_catalog_document(path))


def _get_dimension(catalog: Mapping[str, Mapping[str, Any]], dimension_id: str) -> dict[str, Any]:
    """执行法律题集流程辅助操作。"""
    try:
        dimension = catalog[dimension_id]
    except KeyError as exc:
        raise ValueError(f"未知法律评测维度: {dimension_id}") from exc
    if not isinstance(dimension, Mapping):
        raise ValueError(f"法律评测维度配置无效: {dimension_id}")
    return dict(dimension)


def _first_outcome_marker(text: str) -> int:
    """返回脱敏全文中第一个明确裁判结果标志的位置。"""
    markers = OUTCOME_MARKERS
    positions = [text.find(marker) for marker in markers if text.find(marker) >= 0]
    return min(positions) if positions else -1


def _prediction_external_text(text: str) -> str:
    """移除明确裁判结果区域，作为预测题的额外安全边界。"""
    if not isinstance(text, str):
        return ""
    marker = _first_outcome_marker(text)
    return text[:marker].rstrip() if marker >= 0 else text


def _quote_is_outcome(text: str, quote: str) -> bool:
    """判断引用是否落入或跨入明确裁判结果区域。"""
    if not text or not quote:
        return False
    start = text.find(quote)
    marker = _first_outcome_marker(text)
    if start < 0 or marker < 0:
        return False
    # 不仅拒绝从结果标志之后开始的引用，也拒绝从标志前开始、但跨过结果边界的长引用。
    return start >= marker or start + len(quote) > marker

def _entry_quote(entry: Any) -> str:
    """从事实地图或来源条目中读取连续脱敏引用。"""
    if not isinstance(entry, Mapping):
        return ""
    quote = entry.get("source_quote")
    return quote.strip() if isinstance(quote, str) else ""


def _iter_fact_entries(case: Mapping[str, Any]):
    """只遍历 canonical legal_extraction.case_fact_map。"""
    extraction = case.get("legal_extraction", {})
    extraction = extraction if isinstance(extraction, Mapping) else {}
    nested_map = extraction.get("case_fact_map")
    if not isinstance(nested_map, Mapping):
        nested_map = case.get("fact_map")
    if not isinstance(nested_map, Mapping):
        nested_map = {}
    for field in _FACT_MAP_FIELDS:
        entries = nested_map.get(field)
        if isinstance(entries, list):
            for entry in entries:
                yield field, entry


def _build_source_material(case: Mapping[str, Any], *, exclude_outcome: bool = False) -> list[dict[str, Any]]:
    """从 external_text 和事实地图建立去重后的精确引用材料，不扩展前后文。"""
    full_text = case.get("external_text") or ""
    if not isinstance(full_text, str) or not full_text:
        return []
    materials: list[dict[str, Any]] = []
    seen_quotes: set[str] = set()
    for field, entry in _iter_fact_entries(case):
        quote = _entry_quote(entry)
        if not quote or quote in seen_quotes or quote not in full_text:
            continue
        if exclude_outcome and _quote_is_outcome(full_text, quote):
            continue
        seen_quotes.add(quote)
        materials.append({
            "fact_field": field,
            "source_quote": quote,
            "source_quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        })
    return materials


def _fact_map(case: Mapping[str, Any], *, exclude_outcome: bool = False) -> dict[str, Any]:
    """读取 canonical case_fact_map，并按字段过滤法院结论类字段。

    事实地图是出题模型的输入副本，这里只保留当前接口字段并重新生成引用哈希。

    """
    extraction = case.get("legal_extraction", {})
    extraction = extraction if isinstance(extraction, Mapping) else {}
    nested_map = extraction.get("case_fact_map")
    if not isinstance(nested_map, Mapping):
        nested_map = case.get("fact_map")
    nested_map = nested_map if isinstance(nested_map, Mapping) else {}
    fact_map: dict[str, Any] = {}
    for field in _FACT_MAP_FIELDS:
        if exclude_outcome and field in {"court_found_facts", "court_reasoning", "judgment_results"}:
            continue
        value = nested_map.get(field, [])
        entries: list[dict[str, str]] = []
        if isinstance(value, list):
            for entry in value:
                if not isinstance(entry, Mapping):
                    continue
                text = entry.get("text")
                quote = _entry_quote(entry)
                # 出题材料只能引用当前可见的脱敏全文；预测题的 external_text
                # 已经截断了明确裁判结果区域，因此不在当前文本中的引用必须丢弃。
                if not isinstance(text, str) or not text.strip() or not quote or quote not in str(case.get("external_text") or ""):
                    continue
                entries.append({
                    "text": text.strip(),
                    "source_quote": quote,
                    "source_quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
                })
        fact_map[field] = entries
    return fact_map


def _prediction_safe_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """复制案件，移除三类法院结论事实及明确裁判结果区域。"""
    safe = deepcopy(dict(case))
    external_text = str(safe.get("external_text") or "")
    safe["external_text"] = _prediction_external_text(external_text)
    extraction = safe.get("legal_extraction", {})
    if isinstance(extraction, Mapping):
        safe_map = extraction.get("case_fact_map")
        if isinstance(safe_map, Mapping):
            safe["legal_extraction"] = {"case_fact_map": {
                key: value for key, value in safe_map.items()
                if key not in {"court_found_facts", "court_reasoning", "judgment_results"}
            }}
        else:
            safe["legal_extraction"] = {}
    safe["fact_map"] = _fact_map(safe, exclude_outcome=True)
    safe.pop("full_text", None)
    return safe


def build_generation_input(case: dict[str, Any], dimension_id: str | None = None) -> dict[str, Any]:
    """构造出题模型输入；只暴露 external_text 和脱敏事实地图。"""
    active_case = _prediction_safe_case(case) if dimension_id == "judgment_prediction" else dict(case)
    external_text = active_case.get("external_text")
    if not isinstance(external_text, str) or not external_text.strip():
        raise ValueError("案件缺少 external_text，无法生成候选题")
    defaults = {
        "case_id": "", "classification": {}, "parties": {},
        "cited_statutes": [], "amounts": [], "dates": [], "interest_expressions": [],
        "legal_extraction": {}, "external_text": external_text,
    }
    generation_input = {field: active_case.get(field, defaults[field]) for field in defaults}
    generation_input["fact_map"] = _fact_map(active_case, exclude_outcome=dimension_id == "judgment_prediction")
    generation_input["legal_extraction"] = {"case_fact_map": generation_input["fact_map"]}
    generation_input["source_material"] = _build_source_material(active_case, exclude_outcome=dimension_id == "judgment_prediction")
    generation_input["dimension_id"] = dimension_id or ""
    generation_input.pop("full_text", None)
    return generation_input


_build_generation_input = build_generation_input


def valid_evidence(case: dict[str, Any], evidence: Any, dimension_id: str | None = None) -> list[dict[str, str]]:
    """只保留能在 external_text 中逐字定位的引用，并由本地生成哈希。"""
    external_text = case.get("external_text") if isinstance(case.get("external_text"), str) else ""
    valid: list[dict[str, str]] = []
    if not isinstance(evidence, list):
        return valid
    for item in evidence:
        quote = _entry_quote(item)
        if not quote or quote not in external_text:
            continue
        if dimension_id == "judgment_prediction" and _quote_is_outcome(external_text, quote):
            continue
        valid.append({
            "source_quote": quote,
            "source_quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        })
    return valid


_valid_evidence = valid_evidence

def _prompt_path(template_name: str) -> Path:
    """执行法律题集流程辅助操作。"""
    raw = Path(template_name)
    candidates = []
    if raw.is_absolute():
        candidates.append(raw)
    candidates.extend([
        PROMPT_ROOT / raw,
        PROMPT_ROOT / raw.name,
        _PROJECT_ROOT / raw,
        PROMPT_ROOT / "dimensions" / raw.name,
    ])
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"法律维度 Prompt 不存在: {template_name}")


def _load_dimension_prompt(dimension: Mapping[str, Any]) -> str:
    """执行法律题集流程辅助操作。"""
    path = _prompt_path(str(dimension.get("prompt_template", "")))
    # 通过公共 loader 读取，保持模板编码和读取行为一致。
    return load_template(path.name, path.parent)


def _load_format_prompt(question_format: str) -> str:
    """加载指定题型的出题提示模板。"""
    path = PROMPT_ROOT / "formats" / f"{question_format}.md"
    if not path.is_file():
        raise ValueError(f"题型 Prompt 不存在: {question_format}")
    return path.read_text(encoding="utf-8")


def _format_config(question_format: str) -> dict[str, Any]:
    """读取并返回题型配置。"""
    return _config_get_question_format(question_format)


def _safe_json(value: Any) -> str:
    """执行法律题集流程辅助操作。"""
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _infer_dimension(item: Mapping[str, Any], catalog: Mapping[str, Mapping[str, Any]]) -> str | None:
    """执行法律题集流程辅助操作。"""
    if isinstance(item.get("dimension_id"), str) and item["dimension_id"].strip():
        return item["dimension_id"].strip()
    task_type = item.get("task_type")
    matches = [key for key, value in catalog.items() if value.get("task_type") == task_type]
    return matches[0] if len(matches) == 1 else None


def _contains_answer_leak(item: Mapping[str, Any]) -> bool:
    """执行法律题集流程辅助操作。"""
    answer = str(item.get("reference_answer", "")).strip()
    if len(answer) < 8:
        return False
    question = str(item.get("question", ""))
    context = str(item.get("context", ""))
    return answer in question or answer in context


def _validate_rubric(rubric: Any) -> bool:
    """执行法律题集流程辅助操作。"""
    return isinstance(rubric, Mapping) and all(isinstance(rubric.get(key), list) for key in ("required_points", "bonus_points", "penalties"))


def _normalise_candidate(
    case: Mapping[str, Any], item: Mapping[str, Any], dimension: Mapping[str, Any],
    catalog: Mapping[str, Mapping[str, Any]], dimension_id: str,
    question_format: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """标准化候选题，并执行维度/题型契约校验。"""
    candidate = dict(item)
    inferred = _infer_dimension(candidate, catalog)
    if inferred and inferred != dimension_id:
        return None, f"dimension_id 与请求不一致: {inferred} != {dimension_id}"
    candidate["dimension_id"] = dimension_id
    candidate["task_type"] = candidate.get("task_type") or dimension.get("task_type", "")
    if candidate["task_type"] != dimension.get("task_type"):
        return None, f"task_type 与维度不匹配: {candidate['task_type']}"
    explicit_format = candidate.get("question_format") or question_format
    if explicit_format:
        fmt = explicit_format
    else:
        # 旧候选题没有 question_format；仅在兼容入口中按评分语义推断，
        # 新生成 Prompt 始终要求模型显式返回 question_format。
        legacy_scoring = candidate.get("scoring_method") or dimension.get("scoring_method") or dimension.get("recommended_scoring_method")
        fmt = {"rule": "structured_extraction", "redline": "compliance_response", "rubric_judge": "case_analysis"}.get(legacy_scoring, "case_analysis")
    try:
        fmt_config = _format_config(fmt)
    except Exception as exc:
        return None, str(exc)
    allowed_formats = dimension.get("allowed_question_formats")
    if allowed_formats and fmt not in allowed_formats:
        return None, f"question_format 不适用于维度 {dimension_id}: {fmt}"
    candidate["question_format"] = fmt
    candidate["answer_type"] = candidate.get("answer_type") or fmt_config.get("answer_type") or "结构化论述"
    expected_scoring = fmt_config.get("scoring_method")
    # 新目录统一使用 scoring_method；旧目录曾使用
    # recommended_scoring_method，读取时兼容但输出统一为 scoring_method。
    dimension_scoring = dimension.get("scoring_method") or dimension.get("recommended_scoring_method")
    candidate["scoring_method"] = candidate.get("scoring_method") or expected_scoring or dimension_scoring
    if expected_scoring and candidate["scoring_method"] != expected_scoring:
        return None, f"scoring_method 与题型不匹配: {candidate['scoring_method']} != {expected_scoring}"
    candidate["difficulty"] = candidate.get("difficulty") or "medium"
    candidate["risk_level"] = candidate.get("risk_level") or "low"
    allowed_contexts = dimension.get("context_types") or _CONTEXT_TYPES
    context_type = candidate.get("context_type") or dimension.get("default_context_type")
    if context_type not in allowed_contexts:
        return None, f"context_type 不适用于维度 {dimension_id}: {context_type}"
    candidate["context_type"] = context_type
    if not candidate.get("context"):
        return None, "缺少字段: context（新题必须显式提供独立上下文）"
    context_text = candidate["context"] if isinstance(candidate["context"], str) else json.dumps(candidate["context"], ensure_ascii=False)
    question_text = str(candidate.get("question", ""))
    if context_text.strip() == question_text.strip():
        return None, "context 不能仅重复 question；必须提供独立案件材料"
    missing = [field for field in REQUIRED_FIELDS if not candidate.get(field)]
    if missing:
        return None, f"缺少字段: {', '.join(missing)}"
    if not _validate_rubric(candidate["rubric"]):
        return None, "rubric 必须包含 required_points、bonus_points、penalties 三个数组"
    if _contains_answer_leak(candidate):
        return None, "题面直接包含 reference_answer，疑似泄露答案"
    evidence = valid_evidence(dict(case), candidate.get("source_evidence"), dimension_id)
    if not evidence:
        return None, "source_evidence 无法在脱敏案件全文定位"
    if fmt in {"single_choice", "multiple_choice"}:
        options = candidate.get("options")
        if not isinstance(options, list) or len(options) != 4:
            return None, f"{fmt} 必须有 4 个 options"
        ids = [str(opt.get("option_id")) for opt in options if isinstance(opt, Mapping)]
        if len(ids) != 4 or len(set(ids)) != 4:
            return None, f"{fmt} option_id 必须唯一且有 4 项"
        if fmt == "single_choice":
            if not candidate.get("correct_option") or candidate.get("correct_option") not in ids:
                return None, "single_choice 必须有唯一 correct_option"
        else:
            correct = candidate.get("correct_options")
            if not isinstance(correct, list) or len(correct) < 2 or len(correct) >= len(ids) or not set(correct) <= set(ids):
                return None, "multiple_choice correct_options 必须至少 2 项且不能全选"
        candidate.setdefault("sample_tags", [])
        if "distractor" not in candidate["sample_tags"]:
            candidate["sample_tags"].append("distractor")
    if fmt == "true_false" and candidate.get("correct_answer") not in {True, False, "true", "false"}:
        return None, "true_false 必须有布尔 correct_answer"
    if fmt == "numeric" and candidate.get("numeric_answer") is None:
        return None, "numeric 必须包含 numeric_answer"
    if fmt == "compliance_response":
        req = candidate.get("answer_requirements", {})
        if not isinstance(req, Mapping) or not req.get("must_refuse", True):
            return None, "compliance_response 必须声明拒绝要求"
    if dimension_id == "judgment_prediction":
        context_lower = context_text
        forbidden = ("判决如下", "法院判令", "本院认为", "驳回诉讼请求", "支持原告")
        if any(marker in context_lower for marker in forbidden):
            return None, "裁判结果预测题的 context 泄露了法院最终裁判结果"
    candidate["sample_tags"] = list(dict.fromkeys(candidate.get("sample_tags") or []))
    candidate["error_targets"] = list(dict.fromkeys(candidate.get("error_targets") or []))
    candidate["answer_requirements"] = candidate.get("answer_requirements") or {
        "must_include_conclusion": fmt in {"short_answer", "case_analysis", "legal_drafting"},
        "must_include_reasoning": fmt in {"short_answer", "case_analysis"},
    }
    candidate["source_evidence"] = evidence
    candidate["review_status"] = "pending"
    candidate["case_id"] = case.get("case_id", "")
    candidate["case_classification"] = case.get("classification", {})
    return candidate, None


def generate_for_dimension(
    case: dict[str, Any], client: Any, model: str, dimension_id: str,
    questions_count: int = 1, catalog_path: str | Path | None = None,
    question_format: str | None = None,
    before_model_call: Callable[[], None] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """按维度与可选题型调用统一出题引擎。"""
    catalog = load_dimension_catalog(catalog_path)
    dimension = _get_dimension(catalog, dimension_id)
    if not isinstance(questions_count, int) or questions_count <= 0:
        raise ValueError("questions_count 必须是正整数")
    fmt = question_format or dimension.get("default_question_format")
    if not fmt:
        scoring = dimension.get("scoring_method") or dimension.get("recommended_scoring_method")
        fmt = {
            "rule": "structured_extraction",
            "redline": "compliance_response",
            "rubric_judge": "case_analysis",
        }.get(scoring, "case_analysis")
    fmt_config = _format_config(fmt)
    template = _load_dimension_prompt(dimension)
    format_prompt = _load_format_prompt(fmt)
    generation_input = build_generation_input(case, dimension_id)
    prompt = render(template + "\n\n" + format_prompt, {
        "dimension_id": dimension_id, "task_type": dimension.get("task_type", ""),
        "context_type": dimension.get("default_context_type", ""), "question_format": fmt,
        "questions_count": questions_count, "questions_per_case": questions_count,
        "generation_input": _safe_json(generation_input), "taxonomy": _safe_json(load_taxonomy()),
        "dimension_config": _safe_json(dimension), "format_config": _safe_json(fmt_config),
    })
    if before_model_call is not None:
        before_model_call()
    raw_result = llm_client.call_model(client, model, prompt, 0, 8192)
    raw = raw_result[0] if isinstance(raw_result, (tuple, list)) else raw_result
    value = parse_json_value(raw)
    items = value if isinstance(value, list) else [value]
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            errors.append(f"{dimension_id}/{fmt} 第 {index + 1} 项不是对象")
            continue
        candidate, error = _normalise_candidate(case, item, dimension, catalog, dimension_id, fmt)
        if candidate is None:
            errors.append(f"{dimension_id}/{fmt} 第 {index + 1} 项: {error}")
            continue
        results.append(candidate)
    if len(results) > questions_count:
        errors.append(f"{dimension_id}/{fmt} 返回 {len(results)} 题，超过请求数量 {questions_count}；已截取前者")
        results = results[:questions_count]
    return results, errors


def generate_for_dimension_format(
    case: dict[str, Any], client: Any, model: str, dimension_id: str,
    question_format: str, questions_count: int, catalog_path: str | Path | None = None,
    before_model_call: Callable[[], None] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """按指定维度和题型生成候选题。"""
    return generate_for_dimension(
        case, client, model, dimension_id, questions_count, catalog_path,
        question_format, before_model_call,
    )


def generate_dimension_requests(
    case: dict[str, Any], client: Any, model: str,
    dimension_requests: Mapping[str, int | Mapping[str, Any]] | list[tuple[str, int | Mapping[str, Any]]],
    catalog_path: str | Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """按多个维度/题型逐一生成题目；一个请求失败不会丢弃其他结果。"""

    requests = dimension_requests.items() if isinstance(dimension_requests, Mapping) else dimension_requests
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for dimension_id, count in requests:
        fmt = None
        try:
            if isinstance(count, Mapping):
                fmt = str(count.get("question_format") or "") or None
                count = int(count.get("count", 1))
            generated, dimension_errors = generate_for_dimension(
                case, client, model, str(dimension_id), int(count), catalog_path=catalog_path, question_format=fmt
            )
            results.extend(generated)
            errors.extend(dimension_errors)
        except Exception as exc:
            label = f"{dimension_id}/{fmt}" if fmt else str(dimension_id)
            errors.append(f"{label}: {exc}")
    return results, errors


def load_blueprint_requests(path: str | Path) -> tuple[list[tuple[str, dict[str, Any]]], dict[str, Any]]:
    """读取蓝图并展开为统一的 dimension_id × question_format 请求。

    优先使用交叉配额；没有交叉配额时回退到一级 dimension_quotas。
    返回的请求保留配置顺序，便于稳定复现和在单个请求失败后继续后续请求。
    """

    blueprint_path = Path(path)
    if not blueprint_path.is_file():
        raise FileNotFoundError(f"蓝图文件不存在: {blueprint_path}")
    document = json.loads(blueprint_path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError("--blueprint 必须指向 JSON 对象")

    requests: list[tuple[str, dict[str, Any]]] = []
    cross = document.get("dimension_format_quotas")
    if isinstance(cross, Mapping) and cross:
        for dimension_id, formats in cross.items():
            if not isinstance(formats, Mapping):
                raise ValueError(f"蓝图 dimension_format_quotas.{dimension_id} 必须是对象")
            for question_format, count in formats.items():
                try:
                    count_int = int(count)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"蓝图配额不是整数: {dimension_id}/{question_format}") from exc
                if count_int < 0:
                    raise ValueError(f"蓝图配额不能为负数: {dimension_id}/{question_format}")
                if count_int:
                    requests.append((str(dimension_id), {
                        "question_format": str(question_format), "count": count_int,
                    }))
    else:
        dimensions = document.get("dimension_quotas", document.get("dimension_targets", {}))
        if not isinstance(dimensions, Mapping) or not dimensions:
            raise ValueError("蓝图必须包含非空 dimension_format_quotas 或 dimension_quotas")
        for dimension_id, count in dimensions.items():
            try:
                count_int = int(count)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"蓝图配额不是整数: {dimension_id}") from exc
            if count_int < 0:
                raise ValueError(f"蓝图配额不能为负数: {dimension_id}")
            if count_int:
                requests.append((str(dimension_id), {"count": count_int}))
    if not requests:
        raise ValueError("蓝图没有任何正数生成配额")
    return requests, dict(document)

def _dimension_for_legacy_case(case: Mapping[str, Any], catalog: Mapping[str, Mapping[str, Any]]) -> str:
    """执行法律题集流程辅助操作。"""
    requested = case.get("dimension_id")
    if isinstance(requested, str) and requested in catalog:
        return requested
    task_type = case.get("task_type")
    matches = [key for key, value in catalog.items() if value.get("task_type") == task_type]
    return matches[0] if len(matches) == 1 else "fact_extraction"


def generate_one_case(
    case: dict[str, Any], client: Any, model: str, questions_per_case: int,
    dimension_id: str | None = None, catalog_path: str | Path | None = None,
    before_model_call: Callable[[], None] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """兼容旧的“每案题数”接口；新调用应优先使用维度请求。"""

    catalog = load_dimension_catalog(catalog_path)
    active_dimension = dimension_id or _dimension_for_legacy_case(case, catalog)
    return generate_for_dimension(
        case, client, model, active_dimension, questions_per_case, catalog_path,
        before_model_call=before_model_call,
    )


@dataclass(frozen=True)
class _GenerationTask:
    """表示一个可独立调度的案件、维度与题型生成请求。"""

    task_index: int
    case_index: int
    case: dict[str, Any]
    dimension_id: str | None
    question_format: str | None
    questions_count: int
    legacy_mode: bool = False


def _request_details(task: _GenerationTask) -> tuple[str, str]:
    """返回生成任务的稳定维度和题型元数据标签。"""
    return task.dimension_id or "", task.question_format or ""


def _run_generation_task(
    task: _GenerationTask,
    client: Any,
    model: str,
    catalog_path: str | Path | None,
    limiter: _QPSLimiter | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """执行单个生成任务，并把任务内失败转换为结构化错误。"""
    dimension_id, question_format = _request_details(task)
    try:
        before_model_call = limiter.wait if limiter is not None else None
        if task.legacy_mode:
            generated, task_errors = generate_one_case(
                task.case,
                client,
                model,
                task.questions_count,
                catalog_path=catalog_path,
                before_model_call=before_model_call,
            )
        else:
            generated, task_errors = generate_for_dimension(
                task.case,
                client,
                model,
                dimension_id,
                task.questions_count,
                catalog_path=catalog_path,
                question_format=question_format or None,
                before_model_call=before_model_call,
            )
        structured_errors = [{
            "case_id": task.case.get("case_id", ""),
            "dimension_id": dimension_id,
            "question_format": question_format,
            "error": error,
            "error_type": "generation_validation",
        } for error in task_errors]
        return generated, structured_errors, bool(structured_errors)
    except Exception as exc:
        return [], [{
            "case_id": task.case.get("case_id", ""),
            "dimension_id": dimension_id,
            "question_format": question_format,
            "error": str(exc),
            "error_type": "generation_exception",
        }], True


def _build_generation_tasks(
    eligible_cases: list[dict[str, Any]],
    blueprint_requests: list[tuple[str, dict[str, Any]]] | None,
    dimension_quotas: Mapping[str, int] | None,
    questions_per_case: int,
) -> list[_GenerationTask]:
    """把案件和生成请求展开为顺序稳定、可独立运行的任务。"""
    tasks: list[_GenerationTask] = []
    task_index = 0
    for case_index, case in enumerate(eligible_cases):
        if blueprint_requests is not None:
            requests = [
                (str(dimension_id), request.get("question_format"), int(request.get("count", 0)))
                for dimension_id, request in blueprint_requests
            ]
        elif dimension_quotas:
            requests = []
            for dimension_id, value in dimension_quotas.items():
                if isinstance(value, Mapping):
                    requests.append((
                        str(dimension_id),
                        str(value.get("question_format") or "") or None,
                        int(value.get("count", 1)),
                    ))
                else:
                    requests.append((str(dimension_id), None, int(value)))
        else:
            requests = []

        if requests:
            for dimension_id, question_format, questions_count in requests:
                tasks.append(_GenerationTask(
                    task_index=task_index,
                    case_index=case_index,
                    case=case,
                    dimension_id=dimension_id,
                    question_format=question_format,
                    questions_count=questions_count,
                ))
                task_index += 1
        else:
            tasks.append(_GenerationTask(
                task_index=task_index,
                case_index=case_index,
                case=case,
                dimension_id=None,
                question_format=None,
                questions_count=questions_per_case,
                legacy_mode=True,
            ))
            task_index += 1
    return tasks


def _execute_generation_tasks(
    tasks: list[_GenerationTask],
    client: Any,
    model: str,
    catalog_path: str | Path | None,
    workers: int,
    qps: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """并发执行生成任务，并按照任务提交顺序稳定合并结果。"""
    if not tasks:
        return [], [], 0
    limiter = _QPSLimiter(qps)
    indexed_results: dict[int, tuple[list[dict[str, Any]], list[dict[str, Any]], bool]] = {}

    if workers == 1:
        for task in tasks:
            indexed_results[task.task_index] = _run_generation_task(
                task, client, model, catalog_path, limiter
            )
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_task = {
                executor.submit(_run_generation_task, task, client, model, catalog_path, limiter): task
                for task in tasks
            }
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    indexed_results[task.task_index] = future.result()
                except Exception as exc:
                    dimension_id, question_format = _request_details(task)
                    indexed_results[task.task_index] = ([], [{
                        "case_id": task.case.get("case_id", ""),
                        "dimension_id": dimension_id,
                        "question_format": question_format,
                        "error": str(exc),
                        "error_type": "generation_worker_exception",
                    }], True)

    drafts: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    failed_tasks = 0
    for task in tasks:
        generated, task_errors, failed = indexed_results[task.task_index]
        drafts.extend(generated)
        errors.extend(task_errors)
        failed_tasks += int(failed)
    return drafts, errors, failed_tasks


def run(
    input_path: str | Path, output_path: str | Path, max_items: int | None = None,
    case_ids: set[str] | None = None, questions_per_case: int = 2,
    dimension_quotas: Mapping[str, int] | None = None, catalog_path: str | Path | None = None,
    blueprint_path: str | Path | None = None, allow_needs_review_extraction: bool = False,
    workers: int = 4, qps: float = 3,
) -> list[dict[str, Any]]:
    """批量生成候选题，按案件×维度×题型请求并发调用出题模型。"""

    if workers <= 0:
        raise ValueError("workers must be positive")
    if qps <= 0:
        raise ValueError("qps must be positive")
    if blueprint_path is not None and dimension_quotas is not None:
        raise ValueError("--blueprint 不能与 --dimension-quotas 同时使用")
    blueprint_requests: list[tuple[str, dict[str, Any]]] | None = None
    blueprint: dict[str, Any] | None = None
    if blueprint_path is not None:
        blueprint_requests, blueprint = load_blueprint_requests(blueprint_path)

    cases = read_jsonl(input_path)
    if case_ids:
        cases = [case for case in cases if case.get("case_id") in case_ids]
    if max_items is not None and max_items > 0:
        cases = cases[:max_items]
    errors: list[dict[str, Any]] = []
    eligible_cases: list[dict[str, Any]] = []
    blocked_cases: list[str] = []
    allowed_statuses = {"ready_for_generation", "expert_confirmed"}
    if allow_needs_review_extraction:
        allowed_statuses.update({"needs_review", "rules_fallback"})
    for case in cases:
        quality = case.get("quality", {})
        extraction_quality = quality.get("extraction", {}) if isinstance(quality, Mapping) else {}
        status = extraction_quality.get("review_status") or extraction_quality.get("status")
        if status not in allowed_statuses:
            blocked_cases.append(str(case.get("case_id", "")))
            errors.append({
                "case_id": case.get("case_id", ""),
                "dimension_id": "",
                "question_format": "",
                "error": f"事实地图状态 {status or 'missing'} 不允许进入出题；需要 ready_for_generation 或 expert_confirmed",
                "error_type": "extraction_gate",
            })
        else:
            eligible_cases.append(case)

    client = None
    model = ""
    tasks = _build_generation_tasks(
        eligible_cases, blueprint_requests, dimension_quotas, questions_per_case
    )
    if tasks:
        llm_client.load_env()
        base, key, model = llm_client.read_role("GENERATOR", "deepseek-v4-flash")
        client = llm_client.build_client(base, key)
    drafts, task_errors, failed_tasks = _execute_generation_tasks(
        tasks, client, model, catalog_path, workers, qps
    )
    errors.extend(task_errors)

    write_jsonl(output_path, drafts)
    error_path = Path(output_path).with_suffix(".errors.jsonl")
    write_jsonl(error_path, errors)
    dimension_counts = Counter(str(row.get("dimension_id", "")) for row in drafts if row.get("dimension_id"))
    format_counts = Counter(str(row.get("question_format", "")) for row in drafts if row.get("question_format"))
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for row in drafts:
        dimension = str(row.get("dimension_id", ""))
        question_format = str(row.get("question_format", ""))
        if dimension and question_format:
            grouped[dimension][question_format] += 1
    dimension_format_counts = {dimension: dict(counts) for dimension, counts in grouped.items()}
    metadata = new_run_metadata(
        "legal_benchmark.generation", input=str(input_path), output=str(output_path),
        cases=len(cases), eligible_cases=len(eligible_cases), blocked_extraction_cases=len(blocked_cases),
        questions=len(drafts), errors=len(errors), model=model,
        dimensions=list(dimension_counts), workers=workers, qps=qps,
    )
    metadata.update({
        "blueprint": str(blueprint_path) if blueprint_path else "",
        "blueprint_id": blueprint.get("blueprint_id", "") if blueprint else "",
        "requested_dimension_format_counts": _requested_dimension_format_counts(blueprint_requests),
        "dimension_counts": dict(dimension_counts),
        "question_format_counts": dict(format_counts),
        "dimension_format_counts": dimension_format_counts,
        "error_count": len(errors),
        "used_unconfirmed_extraction": any(
            (case.get("quality", {}).get("extraction", {}).get("review_status")
             or case.get("quality", {}).get("extraction", {}).get("status"))
            in {"needs_review", "rules_fallback"}
            for case in eligible_cases
        ),
        "allow_needs_review_extraction": bool(allow_needs_review_extraction),
        "blocked_extraction_cases": blocked_cases,
        "concurrency_enabled": bool(workers > 1 and len(tasks) > 1),
        "concurrency_unit": "case_dimension_format_request",
        "submitted_tasks": len(tasks),
        "completed_tasks": len(tasks),
        "failed_tasks": failed_tasks,
    })
    Path(output_path).with_suffix(Path(output_path).suffix + ".metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return drafts

def _requested_dimension_format_counts(
    requests: list[tuple[str, dict[str, Any]]] | None,
) -> dict[str, dict[str, int]]:
    """将蓝图展开请求汇总为可读的维度×题型配额。"""
    result: dict[str, Counter[str]] = defaultdict(Counter)
    for dimension_id, request in requests or []:
        question_format = str(request.get("question_format") or "__default__")
        result[str(dimension_id)][question_format] += int(request.get("count", 0))
    return {dimension: dict(counts) for dimension, counts in result.items()}

def _parse_dimension_quotas(value: str) -> dict[str, int] | None:
    """执行法律题集流程辅助操作。"""
    if not value.strip():
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, Mapping):
        raise ValueError("--dimension-quotas 必须是 JSON 对象，例如 {\"rule_application\": 2}")
    return {str(key): int(count) for key, count in parsed.items()}


def main() -> None:
    """执行法律题集流程辅助操作。"""
    parser = argparse.ArgumentParser(description="按法律评测维度生成候选题")
    parser.add_argument("--input", required=True, help="extract 阶段案件 JSONL")
    parser.add_argument("--output", required=True, help="候选题 JSONL")
    parser.add_argument("--max-items", "--max-cases", type=int, default=None, help="只处理前 N 案")
    parser.add_argument("--cases", default="", help="只处理指定 case_id，逗号分隔")
    parser.add_argument("--questions-per-case", type=int, default=2, help="旧兼容模式：每案候选题数量")
    parser.add_argument("--dimension-quotas", default="", help='按维度生成的 JSON 配额，例如 {"rule_application": 2}')
    parser.add_argument("--blueprint", default=None, help="按蓝图中的维度×题型配额生成候选题")
    parser.add_argument("--dimension-catalog", default=None, help="可选维度目录 JSON 路径")
    parser.add_argument("--allow-needs-review-extraction", action="store_true", help="试验性允许使用 needs_review/rules_fallback 事实地图")
    parser.add_argument("--workers", type=int, default=4, help="LLM 最大并发工作线程数，默认 4")
    parser.add_argument("--qps", type=float, default=3, help="LLM 请求启动速率上限，默认每秒 3 次")
    args = parser.parse_args()
    case_ids = {value.strip() for value in args.cases.split(",") if value.strip()} or None
    try:
        rows = run(
            args.input, args.output, args.max_items, case_ids, args.questions_per_case,
            dimension_quotas=_parse_dimension_quotas(args.dimension_quotas),
            catalog_path=args.dimension_catalog,
            blueprint_path=args.blueprint,
            allow_needs_review_extraction=args.allow_needs_review_extraction,
            workers=args.workers,
            qps=args.qps,
        )
        print(f"完成：{args.output}，共 {len(rows)} 道待审候选题")
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
