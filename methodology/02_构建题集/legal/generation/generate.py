"""法律 Benchmark 的统一多维度候选题生成引擎。

本模块只负责 02「构建题集」阶段的候选题生成：

* 用 ``dimension_id`` 路由到对应 Prompt；
* 将完整案件、章节、legal_extraction 和事实地图交给出题模型；
* 对模型返回的题目做轻量结构和原文证据校验；
* 单个维度或单个案件失败时继续处理其他请求。

题目发布后的 ``context`` 与 ``question`` 是 03 模型作答阶段的唯一题面材料，
因此生成模型必须把被测模型需要的材料放进 ``context``，而不是要求被测模型
读取本 Prompt 或依赖未提供的“上文”。
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

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

_CONTEXT_TYPES = {"source_excerpt", "full_document", "self_contained", "scenario"}
_OUTCOME_SECTION_NAMES = {
    "judgment", "judgment_result", "judgment_results", "result", "verdict",
    "裁判结果", "裁判主文", "判决结果", "法院结论", "结论", "court_reasoning",
}
_FACT_MAP_FIELDS = (
    "key_facts", "party_relationships", "claims", "defenses", "evidence",
    "court_found_facts", "procedural_timeline", "applied_laws", "court_reasoning",
    "judgment_results",
)
_LEGAL_EXTRACTION_FIELDS = (
    "legal_issues", "evidence_findings", "conclusions", *_FACT_MAP_FIELDS,
)
REQUIRED_FIELDS = (
    "primary_issue", "task_type", "reasoning_capabilities", "answer_type",
    "scoring_method", "difficulty", "risk_level", "question", "reference_answer",
    "rubric", "source_evidence",
)
NEW_CONTRACT_FIELDS = (
    "dimension_id", "task_type", "context_type", "context", "question",
    "reference_answer", "rubric", "source_evidence",
)
SOURCE_CONTEXT_RADIUS = 240


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


def _source_context(text: str, start: int, end: int) -> str:
    """执行法律题集流程辅助操作。"""
    context_start = max(0, start - SOURCE_CONTEXT_RADIUS)
    context_end = min(len(text), end + SOURCE_CONTEXT_RADIUS)
    return text[context_start:context_end]


def _section_is_outcome(section: Any) -> bool:
    """执行法律题集流程辅助操作。"""
    value = str(section or "").strip().lower()
    return value in {item.lower() for item in _OUTCOME_SECTION_NAMES} or any(
        marker in value for marker in ("judgment", "verdict", "裁判结果", "判决结果", "裁判主文")
    )


def _resolve_source_section(case: Mapping[str, Any], section: Any, quote: str) -> str:
    """执行法律题集流程辅助操作。"""
    sections = case.get("sections", {})
    if not isinstance(sections, Mapping):
        sections = {}
    if isinstance(section, str) and section in sections and quote in str(sections.get(section, "")):
        return section
    for section_name, section_text in sections.items():
        if quote in str(section_text):
            return str(section_name)
    return section.strip() if isinstance(section, str) and section.strip() else "full_text"


def _entry_quote(entry: Any) -> str:
    """执行法律题集流程辅助操作。"""
    if not isinstance(entry, Mapping):
        return ""
    quote = entry.get("source_quote")
    return quote.strip() if isinstance(quote, str) else ""


def _iter_fact_entries(case: Mapping[str, Any]):
    """执行法律题集流程辅助操作。"""
    extraction = case.get("legal_extraction", {})
    if not isinstance(extraction, Mapping):
        extraction = {}
    for field in _LEGAL_EXTRACTION_FIELDS:
        entries = extraction.get(field)
        if isinstance(entries, list):
            for entry in entries:
                yield field, entry
    for field in _FACT_MAP_FIELDS:
        entries = case.get(field)
        if isinstance(entries, list):
            for entry in entries:
                yield field, entry
    for map_name in ("fact_map", "facts_map"):
        nested_map = case.get(map_name)
        if isinstance(nested_map, Mapping):
            for field in _FACT_MAP_FIELDS:
                entries = nested_map.get(field)
                if isinstance(entries, list):
                    for entry in entries:
                        yield field, entry


def _build_source_material(case: Mapping[str, Any], *, exclude_outcome: bool = False) -> list[dict[str, Any]]:
    """从全文和事实地图建立去重后的可追溯原文材料。"""

    full_text = case.get("full_text", "")
    if not isinstance(full_text, str) or not full_text:
        return []
    materials: list[dict[str, Any]] = []
    seen_quotes: set[str] = set()
    for field, entry in _iter_fact_entries(case):
        quote = _entry_quote(entry)
        section = entry.get("source_section") if isinstance(entry, Mapping) else field
        if not quote or quote in seen_quotes or quote not in full_text:
            continue
        resolved_section = _resolve_source_section(case, section, quote)
        if exclude_outcome and _section_is_outcome(resolved_section):
            continue
        start = full_text.find(quote)
        if start < 0:
            continue
        seen_quotes.add(quote)
        materials.append({
            "source_section": resolved_section,
            "source_quote": quote,
            "context": _source_context(full_text, start, start + len(quote)),
        })
    return materials


def _fact_map(case: Mapping[str, Any], *, exclude_outcome: bool = False) -> dict[str, Any]:
    """执行法律题集流程辅助操作。"""
    extraction = case.get("legal_extraction", {})
    extraction = extraction if isinstance(extraction, Mapping) else {}
    nested_map = case.get("fact_map") or case.get("facts_map")
    nested_map = nested_map if isinstance(nested_map, Mapping) else {}
    fact_map: dict[str, Any] = deepcopy(dict(nested_map))
    for field in _FACT_MAP_FIELDS:
        value = case.get(field, extraction.get(field, nested_map.get(field, [])))
        if value is None:
            value = []
        if exclude_outcome and field in {"court_reasoning", "court_found_facts", "judgment_results"}:
            continue
        fact_map[field] = value
    # 保留旧 extraction 字段，避免旧案件只有 legal_extraction 时丢失问题和证据。
    for field in ("legal_issues", "evidence_findings", "conclusions"):
        if field in extraction and not exclude_outcome:
            fact_map[field] = extraction[field]
        elif field in {"legal_issues", "evidence_findings"} and field in extraction:
            fact_map[field] = extraction[field]
    return fact_map


def _prediction_safe_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """复制案件并移除裁判结果，供 judgment_prediction 出题使用。"""

    safe = deepcopy(dict(case))
    sections = safe.get("sections", {})
    if isinstance(sections, Mapping):
        safe["sections"] = {
            key: value for key, value in sections.items() if not _section_is_outcome(key)
        }
        safe_text = "\n\n".join(str(value) for key, value in sections.items() if not _section_is_outcome(key))
        if safe_text.strip():
            safe["full_text"] = safe_text
    else:
        safe_text = str(safe.get("full_text", ""))
    # 对没有 sections 的旧 extract 案件，尽量移除可定位的裁判结果片段。
    extraction_for_redaction = case.get("legal_extraction", {})
    if isinstance(extraction_for_redaction, Mapping):
        outcome_quotes = []
        for field in ("conclusions", "judgment_results"):
            entries = extraction_for_redaction.get(field, [])
            if isinstance(entries, list):
                outcome_quotes.extend(_entry_quote(entry) for entry in entries)
        for quote in sorted((q for q in outcome_quotes if q), key=len, reverse=True):
            safe_text = safe_text.replace(quote, "")
        if not isinstance(sections, Mapping) or not safe.get("sections"):
            safe["full_text"] = safe_text
    extraction = safe.get("legal_extraction", {})
    if isinstance(extraction, Mapping):
        safe["legal_extraction"] = {
            key: value for key, value in extraction.items()
            if key not in {"conclusions", "judgment_results", "court_reasoning"}
        }
    safe["fact_map"] = _fact_map(safe, exclude_outcome=True)
    return safe


def build_generation_input(case: dict[str, Any], dimension_id: str | None = None) -> dict[str, Any]:
    """构造出题模型输入，包含全文、章节、旧 extraction 和事实地图。

    ``judgment_prediction`` 使用裁判结果安全视图；其他维度使用完整案件材料。
    """

    active_case = _prediction_safe_case(case) if dimension_id == "judgment_prediction" else dict(case)
    defaults = {
        "case_id": "", "classification": {}, "facts_summary": "", "parties": {},
        "cited_statutes": [], "amounts": [], "dates": [], "interest_expressions": [],
        "legal_extraction": {}, "full_text": "", "sections": {},
    }
    generation_input = {
        field: active_case.get(field, defaults[field])
        for field in (*defaults.keys(),)
    }
    generation_input["fact_map"] = _fact_map(active_case, exclude_outcome=dimension_id == "judgment_prediction")
    generation_input["source_material"] = _build_source_material(
        active_case, exclude_outcome=dimension_id == "judgment_prediction"
    )
    generation_input["dimension_id"] = dimension_id or ""
    return generation_input


# 早期调用方使用私有名字；保留别名。
_build_generation_input = build_generation_input


def valid_evidence(case: dict[str, Any], evidence: Any, dimension_id: str | None = None) -> list[dict[str, str]]:
    """只保留可在案件全文定位的原文证据，并修正错误章节标签。"""

    full_text = case.get("full_text", "")
    if not isinstance(full_text, str):
        full_text = ""
    valid: list[dict[str, str]] = []
    if not isinstance(evidence, list):
        return valid
    for item in evidence:
        if not isinstance(item, Mapping):
            continue
        quote = _entry_quote(item)
        if not quote or quote not in full_text:
            continue
        section = _resolve_source_section(case, item.get("source_section"), quote)
        if dimension_id == "judgment_prediction" and _section_is_outcome(section):
            continue
        valid.append({"source_section": section, "source_quote": quote})
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
) -> tuple[dict[str, Any] | None, str | None]:
    """执行法律题集流程辅助操作。"""
    candidate = dict(item)
    inferred = _infer_dimension(candidate, catalog)
    if inferred and inferred != dimension_id:
        return None, f"dimension_id 与请求不一致: {inferred} != {dimension_id}"
    candidate["dimension_id"] = dimension_id
    candidate["task_type"] = candidate.get("task_type") or dimension.get("task_type", "")
    if candidate["task_type"] != dimension.get("task_type"):
        return None, f"task_type 与维度不匹配: {candidate['task_type']}"
    candidate["reasoning_capabilities"] = candidate.get("reasoning_capabilities") or dimension.get("reasoning_capabilities", [])
    candidate["answer_type"] = candidate.get("answer_type") or "长答案"
    candidate["scoring_method"] = candidate.get("scoring_method") or dimension.get("scoring_method") or dimension.get("recommended_scoring_method", "rubric_judge")
    candidate["difficulty"] = candidate.get("difficulty") or "medium"
    candidate["risk_level"] = candidate.get("risk_level") or "low"
    candidate["primary_issue"] = candidate.get("primary_issue") or dimension.get("task_type", dimension_id)
    expected_scoring = dimension.get("scoring_method") or dimension.get("recommended_scoring_method")
    if expected_scoring and candidate["scoring_method"] != expected_scoring:
        return None, f"scoring_method 与维度不匹配: {candidate['scoring_method']}"
    allowed_contexts = dimension.get("context_types") or _CONTEXT_TYPES
    context_type = candidate.get("context_type") or dimension.get("default_context_type")
    if context_type not in allowed_contexts:
        return None, f"context_type 不适用于维度 {dimension_id}: {context_type}"
    candidate["context_type"] = context_type
    # 新题必须把被测模型需要的材料显式放在 context 中；不能再把 question
    # 自动复制成 context，否则题面看似完整，实际上仍依赖生成阶段的隐藏上文。
    if not candidate.get("context"):
        return None, "缺少字段: context（新题必须显式提供独立上下文）"
    context_text = candidate["context"] if isinstance(candidate["context"], str) else json.dumps(candidate["context"], ensure_ascii=False)
    question_text = str(candidate.get("question", ""))
    if context_text.strip() == question_text.strip():
        return None, "context 不能仅重复 question；请提供独立案件材料"
    missing = [field for field in REQUIRED_FIELDS if not candidate.get(field)]
    if missing:
        return None, f"缺少字段: {', '.join(missing)}"
    if not _validate_rubric(candidate["rubric"]):
        return None, "rubric 必须包含 required_points、bonus_points、penalties 三个数组"
    if _contains_answer_leak(candidate):
        return None, "题面直接包含 reference_answer，疑似泄露答案"
    evidence = valid_evidence(dict(case), candidate.get("source_evidence"), dimension_id)
    if not evidence:
        return None, "source_evidence 无法在案件全文定位"
    if dimension_id == "judgment_prediction":
        outcome_values = []
        sections = case.get("sections", {})
        if isinstance(sections, Mapping):
            outcome_values.extend(str(value) for key, value in sections.items() if _section_is_outcome(key))
        if any(value and value in str(candidate.get("context", "")) for value in outcome_values):
            return None, "裁判结果预测题的 context 泄露了法院最终裁判结果"
    candidate["source_evidence"] = evidence
    candidate["review_status"] = "pending"
    candidate["case_id"] = case.get("case_id", "")
    candidate["case_classification"] = case.get("classification", {})
    return candidate, None


def generate_for_dimension(
    case: dict[str, Any], client: Any, model: str, dimension_id: str,
    questions_count: int = 1, catalog_path: str | Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """按一个维度调用对应 Prompt，返回有效候选题和该维度错误。"""

    catalog = load_dimension_catalog(catalog_path)
    dimension = _get_dimension(catalog, dimension_id)
    if not isinstance(questions_count, int) or questions_count <= 0:
        raise ValueError("questions_count 必须是正整数")
    template = _load_dimension_prompt(dimension)
    generation_input = build_generation_input(case, dimension_id)
    prompt = render(template, {
        "dimension_id": dimension_id,
        "task_type": dimension.get("task_type", ""),
        "context_type": dimension.get("default_context_type", ""),
        "questions_count": questions_count,
        "questions_per_case": questions_count,
        "generation_input": _safe_json(generation_input),
        "taxonomy": _safe_json(load_taxonomy()),
        "dimension_config": _safe_json(dimension),
    })
    raw_result = llm_client.call_model(client, model, prompt, 0, 8192)
    raw = raw_result[0] if isinstance(raw_result, (tuple, list)) else raw_result
    value = parse_json_value(raw)
    items = value if isinstance(value, list) else [value]
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            errors.append(f"{dimension_id} 第 {index + 1} 项不是对象")
            continue
        candidate, error = _normalise_candidate(case, item, dimension, catalog, dimension_id)
        if candidate is None:
            errors.append(f"{dimension_id} 第 {index + 1} 项: {error}")
            continue
        results.append(candidate)
    if len(results) > questions_count:
        errors.append(f"{dimension_id} 返回 {len(results)} 题，超过请求数量 {questions_count}；已截取前者")
        results = results[:questions_count]
    return results, errors


def generate_dimension_requests(
    case: dict[str, Any], client: Any, model: str,
    dimension_requests: Mapping[str, int] | list[tuple[str, int]],
    catalog_path: str | Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """按多个维度逐一生成题目；一个维度失败不会丢弃其他维度结果。"""

    requests = dimension_requests.items() if isinstance(dimension_requests, Mapping) else dimension_requests
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for dimension_id, count in requests:
        try:
            generated, dimension_errors = generate_for_dimension(
                case, client, model, str(dimension_id), int(count), catalog_path=catalog_path
            )
            results.extend(generated)
            errors.extend(dimension_errors)
        except Exception as exc:
            errors.append(f"{dimension_id}: {exc}")
    return results, errors


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
) -> tuple[list[dict[str, Any]], list[str]]:
    """兼容旧的“每案题数”接口；新调用应优先使用维度请求。"""

    catalog = load_dimension_catalog(catalog_path)
    active_dimension = dimension_id or _dimension_for_legacy_case(case, catalog)
    return generate_for_dimension(case, client, model, active_dimension, questions_per_case, catalog_path)


def run(
    input_path: str | Path, output_path: str | Path, max_items: int | None = None,
    case_ids: set[str] | None = None, questions_per_case: int = 2,
    dimension_quotas: Mapping[str, int] | None = None, catalog_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """批量生成候选题。

    传入 ``dimension_quotas`` 时按维度独立调用；未传入时保留旧的
    ``questions_per_case`` 兼容行为，并按案件已有 task_type 推断一个维度。
    """

    cases = read_jsonl(input_path)
    if case_ids:
        cases = [case for case in cases if case.get("case_id") in case_ids]
    if max_items is not None and max_items > 0:
        cases = cases[:max_items]
    llm_client.load_env()
    base, key, model = llm_client.read_role("GENERATOR", "deepseek-v4-flash")
    client = llm_client.build_client(base, key)
    drafts: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        print(f"[出题] {index}/{len(cases)} {case.get('case_id', '')}")
        try:
            if dimension_quotas:
                generated, case_errors = generate_dimension_requests(
                    case, client, model, dimension_quotas, catalog_path=catalog_path
                )
            else:
                generated, case_errors = generate_one_case(
                    case, client, model, questions_per_case, catalog_path=catalog_path
                )
            drafts.extend(generated)
            errors.extend({"case_id": case.get("case_id"), "error": error} for error in case_errors)
        except Exception as exc:
            errors.append({"case_id": case.get("case_id"), "error": str(exc)})
    write_jsonl(output_path, drafts)
    error_path = Path(output_path).with_suffix(".errors.jsonl")
    write_jsonl(error_path, errors)
    metadata = new_run_metadata(
        "legal_benchmark.generation", input=str(input_path), output=str(output_path),
        cases=len(cases), questions=len(drafts), errors=len(errors), model=model,
        dimensions=list(dimension_quotas) if dimension_quotas else [],
    )
    Path(output_path).with_suffix(Path(output_path).suffix + ".metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return drafts


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
    parser.add_argument("--dimension-catalog", default=None, help="可选维度目录 JSON 路径")
    args = parser.parse_args()
    case_ids = {value.strip() for value in args.cases.split(",") if value.strip()} or None
    try:
        rows = run(
            args.input, args.output, args.max_items, case_ids, args.questions_per_case,
            dimension_quotas=_parse_dimension_quotas(args.dimension_quotas),
            catalog_path=args.dimension_catalog,
        )
        print(f"完成：{args.output}，共 {len(rows)} 道待审候选题")
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
