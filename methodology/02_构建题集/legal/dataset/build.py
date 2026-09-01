"""法律正式题集组装模块。

候选题先经过字段、taxonomy、题型和案件级校验，再依据蓝图的维度、题型、难度、风险
和专项标签配额组装 release。配额不足会显式写入 coverage，不静默复制或伪造题目。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from core.data_io import read_jsonl, write_jsonl
from core.run_metadata import new_run_metadata
from .split import assign_case_splits

_taxonomy = importlib.import_module("methodology.01_造Benchmark.legal.taxonomy")
allowed_values = _taxonomy.allowed_values
load_taxonomy = _taxonomy.load_taxonomy
validate_cause_path = _taxonomy.validate_cause_path
_config = importlib.import_module("methodology.02_构建题集.legal.config")
_load_format_catalog = _config.load_question_format_catalog

CONFIG_ROOT = Path(__file__).resolve().parents[1] / "config"
DEFAULT_CATALOG_PATH = CONFIG_ROOT / "dimension_catalog.json"
DEFAULT_BLUEPRINT_PATH = CONFIG_ROOT / "dataset_blueprint.json"
REQUIRED_FIELDS = (
    "case_id", "dimension_id", "context_type", "context", "task_type",
    "answer_type", "scoring_method", "difficulty", "risk_level",
    "question", "reference_answer", "rubric", "source_evidence", "case_classification",
)


def _read_json(path: str | Path) -> dict[str, Any]:
    """读取 JSON 配置文件。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_dimension_catalog(path: str | Path | None = None) -> dict[str, Any]:
    """读取维度目录并校验 dimension_id 唯一。"""
    catalog = _read_json(path or DEFAULT_CATALOG_PATH)
    dimensions = catalog.get("dimensions", [])
    if not isinstance(dimensions, list) or not dimensions:
        raise ValueError("dimension_catalog 必须包含非空 dimensions 数组")
    ids = [str(item.get("dimension_id", "")) for item in dimensions if isinstance(item, dict)]
    if len(ids) != len(dimensions) or any(not item for item in ids):
        raise ValueError("dimension_catalog 中存在缺失 dimension_id 的维度")
    duplicates = sorted(key for key, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"dimension_id 重复：{duplicates}")
    return catalog


def _dimension_map(catalog: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """把维度目录转换为 dimension_id 索引。"""
    source = catalog or load_dimension_catalog()
    return {str(item["dimension_id"]): item for item in source.get("dimensions", [])}


def load_blueprint(path: str | Path | None = None, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    """读取蓝图；未指定文件时回退到默认蓝图或目录内嵌蓝图。"""
    target = Path(path) if path else DEFAULT_BLUEPRINT_PATH
    if target.is_file():
        return _read_json(target)
    source = catalog or load_dimension_catalog()
    embedded = source.get("blueprint")
    if isinstance(embedded, dict):
        return embedded
    return {"version": "1.0.0", "dimension_quotas": {
        str(item["dimension_id"]): int(item.get("target_count", 0) or 0)
        for item in source.get("dimensions", [])
    }}


def _quota_section(blueprint: Mapping[str, Any] | None, *names: str) -> dict[str, int]:
    """读取允许字典或列表形式的一级配额。"""
    if not blueprint:
        return {}
    raw: Any = None
    for name in names:
        if name in blueprint:
            raw = blueprint[name]
            break
    if isinstance(raw, list):
        result = {}
        for item in raw:
            if isinstance(item, Mapping) and item.get("id", item.get("dimension_id", item.get("question_format"))):
                key = item.get("id", item.get("dimension_id", item.get("question_format")))
                result[str(key)] = int(item.get("target_count", item.get("count", 0)) or 0)
        return result
    if isinstance(raw, Mapping):
        result = {}
        for key, value in raw.items():
            if isinstance(value, Mapping):
                value = value.get("target_count", value.get("count", 0))
            result[str(key)] = int(value or 0)
        return result
    return {}


def _quota_map(blueprint: dict[str, Any] | None) -> dict[str, int]:
    """读取维度配额，保留旧的兼容接口。"""
    return _quota_section(blueprint, "dimension_quotas", "dimension_targets", "quotas")


def _dimension_format_quotas(blueprint: Mapping[str, Any] | None) -> dict[str, dict[str, int]]:
    """读取维度与题型交叉配额。"""
    raw = (blueprint or {}).get("dimension_format_quotas", {})
    result: dict[str, dict[str, int]] = {}
    if isinstance(raw, Mapping):
        for dimension, formats in raw.items():
            if isinstance(formats, Mapping):
                result[str(dimension)] = {str(fmt): int(value or 0) for fmt, value in formats.items()}
    return result


def _allowed_context_types(config: dict[str, Any]) -> set[str]:
    """读取某一维度允许的 context_type。"""
    values = config.get("allowed_context_types", config.get("context_types", []))
    if isinstance(values, str):
        values = [values]
    if not values and config.get("context_type"):
        values = [config["context_type"]]
    if not values and config.get("default_context_type"):
        values = [config["default_context_type"]]
    return {str(value) for value in values}


def _normalise_format(row: Mapping[str, Any]) -> str:
    """读取题型；旧候选题按评分方式推导兼容题型。"""
    fmt = str(row.get("question_format") or "").strip()
    if fmt:
        return fmt
    method = str(row.get("scoring_method") or "")
    return "compliance_response" if method == "redline" else ("case_analysis" if method == "rubric_judge" else "structured_extraction")


def _taxonomy_valid(row: dict[str, Any], catalog: dict[str, Any] | None = None) -> bool:
    """验证题目字段、案件分类、维度、题型和标签是否属于受控配置。"""
    classification = row.get("case_classification")
    if not isinstance(classification, dict):
        return False
    for field, taxonomy_field in (("task_type", "task_types"), ("answer_type", "answer_types"),
                                  ("scoring_method", "scoring_methods"), ("difficulty", "difficulties"),
                                  ("risk_level", "risk_levels")):
        if row.get(field) not in allowed_values(taxonomy_field):
            return False
    dimensions = _dimension_map(catalog)
    dimension = dimensions.get(str(row.get("dimension_id", "")))
    if not dimension or row.get("task_type") != dimension.get("task_type"):
        return False
    fmt = _normalise_format(row)
    try:
        fmt_config = _load_format_catalog().get("formats", {}).get(fmt, {})
    except Exception:
        fmt_config = {}
    if not fmt_config:
        return False
    if row.get("scoring_method") != fmt_config.get("scoring_method"):
        return False
    allowed_formats = dimension.get("allowed_question_formats") or dimension.get("question_formats") or []
    if allowed_formats and fmt not in allowed_formats:
        return False
    if not row.get("context") or str(row.get("context")).strip() == str(row.get("question") or "").strip():
        return False
    if _allowed_context_types(dimension) and row.get("context_type") not in _allowed_context_types(dimension):
        return False
    classification_checks = (("domain", "domains"), ("procedure_stage", "procedure_stages"),
                              ("document_type", "document_types"), ("primary_category", "primary_categories"))
    for field, taxonomy_field in classification_checks:
        if classification.get(field) not in allowed_values(taxonomy_field):
            return False
    if not validate_cause_path(classification.get("primary_category", ""), classification.get("cause_path", [])):
        return False
    if any(value not in allowed_values("procedure_tags") for value in classification.get("procedure_tags", [])):
        return False
    if any(value not in allowed_values("evidence_tags") for value in classification.get("evidence_tags", [])):
        return False
    if any(value not in allowed_values("sample_tags") for value in row.get("sample_tags", []) or []):
        return False
    if any(value not in allowed_values("error_types") for value in row.get("error_targets", []) or []):
        return False
    applicable = dimension.get("applicable_case_types", [])
    return not applicable or "*" in applicable or classification.get("primary_category") in applicable


def _accepted_sort_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    """返回与输入顺序无关的稳定候选题排序键。"""
    return (
        str(row.get("dimension_id", "")),
        str(row.get("question_format") or _normalise_format(row)),
        str(row.get("case_id", "")),
        str(row.get("question", "")),
        str(row.get("question_id") or _row_key(row)),
    )


def _row_key(row: Mapping[str, Any]) -> str:
    """生成去重键，避免候选题重复进入 release。"""
    explicit = str(row.get("question_id") or "").strip()
    if explicit:
        return explicit
    raw = "|".join(str(row.get(key, "")) for key in ("case_id", "dimension_id", "question_format", "question", "context"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _counts(rows: list[dict[str, Any]], field: str) -> Counter[str]:
    """统计普通字段。"""
    return Counter(str(row.get(field) or "未标注") for row in rows)


def _split_targets(blueprint: Mapping[str, Any], target_total: int) -> dict[str, int]:
    """读取显式 split 配额，或把 split_ratios 换算为整数目标。"""
    explicit = _quota_section(blueprint, "split_quotas", "split_targets")
    if explicit:
        return explicit
    ratios = blueprint.get("split_ratios", {})
    if not isinstance(ratios, Mapping) or not ratios or target_total <= 0:
        return {}
    keys = list(ratios)
    raw = {str(key): max(0.0, float(ratios[key])) * target_total for key in keys}
    result = {key: int(value) for key, value in raw.items()}
    remainder = target_total - sum(result.values())
    order = sorted(keys, key=lambda key: (raw[str(key)] - result[str(key)], str(key)), reverse=True)
    for key in order[:max(0, remainder)]:
        result[str(key)] += 1
    return result


def dimension_coverage(rows: list[dict[str, Any]], blueprint: dict[str, Any] | None = None) -> dict[str, Any]:
    """生成维度、题型、案件类别、split、难度、风险、标签和缺口覆盖报告。"""
    blueprint = blueprint or {}
    dimension_counts = _counts(rows, "dimension_id")
    format_counts = _counts(rows, "question_format")
    difficulty_counts = _counts(rows, "difficulty")
    risk_counts = _counts(rows, "risk_level")
    split_counts = _counts(rows, "split")
    category_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    dimension_format_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        cls = row.get("case_classification") if isinstance(row.get("case_classification"), Mapping) else {}
        category_counts[str(cls.get("primary_category") or row.get("case_category") or "未分类")] += 1
        tags = row.get("sample_tags") if isinstance(row.get("sample_tags"), list) else []
        tag_counts.update(str(tag) for tag in tags)
        dimension_format_counts[str(row.get("dimension_id", "未标注"))][str(row.get("question_format") or _normalise_format(row))] += 1
    dim_quota = _quota_map(blueprint)
    fmt_quota = _quota_section(blueprint, "question_format_quotas", "format_quotas")
    cross_quota = _dimension_format_quotas(blueprint)
    difficulty_quota = _quota_section(blueprint, "difficulty_quotas")
    risk_quota = _quota_section(blueprint, "risk_quotas")
    tag_minimums = _quota_section(blueprint, "tag_minimums", "tag_quotas")
    case_type_minimums = _quota_section(blueprint, "case_type_minimum_counts", "case_category_minimum_counts")
    target_total = int(blueprint.get("target_total", 0) or 0)
    split_targets = _split_targets(blueprint, target_total)
    shortages: dict[str, int] = {}
    for key, target in dim_quota.items():
        if target > dimension_counts.get(key, 0): shortages[f"dimension:{key}"] = target - dimension_counts.get(key, 0)
    for key, target in fmt_quota.items():
        if target > format_counts.get(key, 0): shortages[f"question_format:{key}"] = target - format_counts.get(key, 0)
    for dim, formats in cross_quota.items():
        for fmt, target in formats.items():
            actual = dimension_format_counts.get(dim, {}).get(fmt, 0)
            if target > actual: shortages[f"dimension_format:{dim}:{fmt}"] = target - actual
    for key, target in difficulty_quota.items():
        if target > difficulty_counts.get(key, 0): shortages[f"difficulty:{key}"] = target - difficulty_counts.get(key, 0)
    for key, target in risk_quota.items():
        if target > risk_counts.get(key, 0): shortages[f"risk:{key}"] = target - risk_counts.get(key, 0)
    for key, target in tag_minimums.items():
        if target > tag_counts.get(key, 0): shortages[f"tag:{key}"] = target - tag_counts.get(key, 0)
    case_type_shortages: dict[str, int] = {}
    for key, target in case_type_minimums.items():
        actual = category_counts.get(key, 0)
        if target > actual:
            case_type_shortages[key] = target - actual
            shortages[f"case_type:{key}"] = target - actual
    split_shortages: dict[str, int] = {}
    for key, target in split_targets.items():
        actual = split_counts.get(key, 0)
        if target > actual:
            split_shortages[key] = target - actual
            shortages[f"split:{key}"] = target - actual
    if target_total > len(rows): shortages["total"] = target_total - len(rows)
    return {
        "total_count": len(rows), "target_total": target_total,
        "dimension_counts": dict(dimension_counts), "dimension_quotas": dim_quota,
        "question_format_counts": dict(format_counts), "question_format_quotas": fmt_quota,
        "dimension_format_counts": {key: dict(value) for key, value in dimension_format_counts.items()},
        "dimension_format_quotas": cross_quota, "difficulty_counts": dict(difficulty_counts),
        "difficulty_quotas": difficulty_quota, "risk_counts": dict(risk_counts), "risk_quotas": risk_quota,
        "tag_counts": dict(tag_counts), "tag_minimums": tag_minimums,
        "category_counts": dict(category_counts), "case_type_minimums": case_type_minimums,
        "case_type_shortages": case_type_shortages, "split_counts": dict(split_counts),
        "split_targets": split_targets, "split_shortages": split_shortages,
        "quota_shortages": shortages, "incomplete": bool(shortages), "quota_satisfied": not shortages,
    }

def _selection_category(row: Mapping[str, Any]) -> str:
    """读取候选题对应的案件主分类，用于补足案件类别覆盖。"""
    classification = row.get("case_classification")
    if isinstance(classification, Mapping):
        value = classification.get("primary_category")
        if value:
            return str(value)
    return str(row.get("case_category") or "未分类")


def _selection_format(row: Mapping[str, Any]) -> str:
    """读取候选题题型，并兼容旧候选题。"""
    return str(row.get("question_format") or _normalise_format(row))


def _selection_score(
    row: Mapping[str, Any],
    selected: list[dict[str, Any]],
    blueprint: Mapping[str, Any],
    stage: str,
    stable_index: int,
) -> tuple[int, ...]:
    """计算候选题在当前贪心阶段的动态覆盖优先级。

    分数按缺口层级排列，元组越大越优先。``stage`` 只决定当前贪心阶段的
    第一优先级，后续优先级始终按维度/题型、难度、风险、标签、案件类别、
    split 和新案件顺序补足。最后使用稳定索引反向排序，保证同一输入集合
    每次得到相同结果。
    """
    dimension = str(row.get("dimension_id", ""))
    question_format = _selection_format(row)
    difficulty = str(row.get("difficulty") or "未标注")
    risk = str(row.get("risk_level") or "未标注")
    category = _selection_category(row)
    split = str(row.get("split") or "")
    tags = {
        str(tag)
        for tag in (row.get("sample_tags") if isinstance(row.get("sample_tags"), list) else [])
    }

    dimension_counts = Counter(str(item.get("dimension_id", "")) for item in selected)
    format_counts = Counter(_selection_format(item) for item in selected)
    dimension_format_counts = Counter(
        (str(item.get("dimension_id", "")), _selection_format(item)) for item in selected
    )
    difficulty_counts = Counter(str(item.get("difficulty") or "未标注") for item in selected)
    risk_counts = Counter(str(item.get("risk_level") or "未标注") for item in selected)
    tag_counts: Counter[str] = Counter()
    category_counts = Counter(_selection_category(item) for item in selected)
    split_counts = Counter(str(item.get("split") or "") for item in selected if item.get("split"))
    selected_case_ids = {str(item.get("case_id") or "") for item in selected}
    for item in selected:
        item_tags = item.get("sample_tags") if isinstance(item.get("sample_tags"), list) else []
        tag_counts.update(str(tag) for tag in item_tags)

    dimension_quotas = _quota_map(dict(blueprint))
    format_quotas = _quota_section(blueprint, "question_format_quotas", "format_quotas")
    cross_quotas = _dimension_format_quotas(blueprint)
    difficulty_quotas = _quota_section(blueprint, "difficulty_quotas")
    risk_quotas = _quota_section(blueprint, "risk_quotas")
    tag_minimums = _quota_section(blueprint, "tag_minimums", "tag_quotas")
    category_minimums = _quota_section(
        blueprint, "case_type_minimum_counts", "case_category_minimum_counts"
    )
    split_targets = _split_targets(blueprint, int(blueprint.get("target_total", 0) or 0))

    cross_gain = int(
        dimension_format_counts[(dimension, question_format)]
        < cross_quotas.get(dimension, {}).get(question_format, 0)
    )
    dimension_gain = int(dimension_counts[dimension] < dimension_quotas.get(dimension, 0))
    format_gain = int(format_counts[question_format] < format_quotas.get(question_format, 0))
    difficulty_gain = int(difficulty_counts[difficulty] < difficulty_quotas.get(difficulty, 0))
    risk_gain = int(risk_counts[risk] < risk_quotas.get(risk, 0))
    tag_gain = sum(1 for tag in tags if tag_counts[tag] < tag_minimums.get(tag, 0))
    category_gain = int(category_counts[category] < category_minimums.get(category, 0))
    split_gain = int(bool(split) and split_counts[split] < split_targets.get(split, 0))

    # 候选题通常在 split 分配前没有 split 字段。此时优先选择尚未出现的案件，
    # 为后续 assign_case_splits 保留跨案件分层的空间；已有 split 时仍以显式
    # split 缺口为更高优先级。
    new_case_gain = int(
        bool(split_targets) and str(row.get("case_id") or "") not in selected_case_ids
    )

    if stage == "cross":
        primary = (cross_gain, dimension_gain, format_gain)
    elif stage == "dimension":
        primary = (dimension_gain, format_gain)
    elif stage == "format":
        primary = (format_gain, dimension_gain)
    else:
        primary = (cross_gain, dimension_gain, format_gain)

    return (*primary, difficulty_gain, risk_gain, tag_gain, category_gain, split_gain, new_case_gain, -stable_index)


def _select_with_quotas(
    candidates: list[dict[str, Any]], blueprint: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按分层缺口动态排序，保留交叉配额→一级配额→总量的贪心语义。"""
    dim_quota = _quota_map(blueprint)
    fmt_quota = _quota_section(blueprint, "question_format_quotas", "format_quotas")
    cross = _dimension_format_quotas(blueprint)
    target_total = int(blueprint.get("target_total", 0) or 0)
    ordered = sorted(candidates, key=_accepted_sort_key)
    selected: list[dict[str, Any]] = []
    used: set[str] = set()

    def take(predicate, limit=None, stage="total"):
        """从符合条件的候选中逐题选择当前覆盖收益最高且不重复的题目。"""
        count = 0
        while limit is None or count < limit:
            available = [
                (index, row)
                for index, row in enumerate(ordered)
                if _row_key(row) not in used and predicate(row)
            ]
            if not available:
                break
            index, row = max(
                available,
                key=lambda item: _selection_score(item[1], selected, blueprint, stage, item[0]),
            )
            selected.append(row)
            used.add(_row_key(row))
            count += 1
        return count

    # 保留原有阶段边界；只把每个阶段内的固定顺序改成动态缺口优先。
    for dim, formats in cross.items():
        for fmt, target in formats.items():
            take(
                lambda row, d=dim, f=fmt: str(row.get("dimension_id")) == d
                and _selection_format(row) == f,
                target,
                stage="cross",
            )
    for dim, target in dim_quota.items():
        current = sum(1 for row in selected if str(row.get("dimension_id")) == dim)
        take(
            lambda row, d=dim: str(row.get("dimension_id")) == d,
            max(0, target - current),
            stage="dimension",
        )
    for fmt, target in fmt_quota.items():
        current = sum(1 for row in selected if _selection_format(row) == fmt)
        take(
            lambda row, f=fmt: _selection_format(row) == f,
            max(0, target - current),
            stage="format",
        )
    if target_total:
        take(lambda row: True, max(0, target_total - len(selected)), stage="total")
    else:
        take(lambda row: True, None, stage="total")

    rejected = [row for row in ordered if _row_key(row) not in used]
    return selected, rejected


def build_release(drafts: list[dict[str, Any]], include_pending: bool = False, max_items: int | None = None,
                  blueprint: dict[str, Any] | None = None, catalog: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """过滤候选题并按蓝图配额组装 release。"""
    catalog = catalog or load_dimension_catalog()
    blueprint = blueprint or load_blueprint(catalog=catalog)
    valid: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for draft in drafts:
        if not include_pending and draft.get("review_status") != "approved":
            continue
        row = dict(draft)
        row["question_format"] = _normalise_format(row)
        missing = [field for field in REQUIRED_FIELDS if not row.get(field)]
        key = _row_key(row)
        if key in seen:
            rejected.append({"case_id": row.get("case_id", ""), "question": row.get("question", ""), "reason": "重复候选题"})
        elif missing or not _taxonomy_valid(row, catalog):
            rejected.append({"case_id": row.get("case_id", ""), "dimension_id": row.get("dimension_id", ""), "question": row.get("question", ""), "reason": f"missing={missing}; taxonomy_valid={_taxonomy_valid(row, catalog)}"})
        else:
            seen.add(key); valid.append(row)
    selected, extras = _select_with_quotas(valid, blueprint)
    for row in extras:
        rejected.append({"case_id": row.get("case_id", ""), "dimension_id": row.get("dimension_id", ""), "question_format": row.get("question_format", ""), "question": row.get("question", ""), "reason": "蓝图配额筛选未入选"})
    selected.sort(key=_accepted_sort_key)
    if max_items is not None and max_items > 0 and len(selected) > max_items:
        for row in selected[max_items:]:
            rejected.append({"case_id": row.get("case_id", ""), "dimension_id": row.get("dimension_id", ""), "question": row.get("question", ""), "reason": f"max_items exceeded: {max_items}"})
        selected = selected[:max_items]
    counters: Counter[str] = Counter()
    for row in selected:
        case_id = str(row.get("case_id", "")); counters[case_id] += 1
        row["question_id"] = str(row.get("question_id") or f"legal_{case_id.removeprefix('case_')}_{counters[case_id]:02d}")
        row["version"] = "1.0.0"; row["release_date"] = date.today().isoformat()
    selected = assign_case_splits(selected, split_ratios=dict(blueprint.get("split_ratios", {})) or None)
    return selected, rejected, dimension_coverage(selected, blueprint)


def build(drafts: list[dict[str, Any]], include_pending: bool = False, max_items: int | None = None,
          blueprint: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """兼容旧接口，返回正式题目和拒绝记录。"""
    accepted, rejected, _ = build_release(drafts, include_pending, max_items, blueprint)
    return accepted, rejected


def _write_coverage_report(path: Path, coverage: dict[str, Any], rejected: list[dict[str, Any]]) -> None:
    """写出包含实际值、目标值和缺口的人类可读覆盖报告。"""
    def table_section(title: str, counts: Mapping[str, Any], targets: Mapping[str, Any] | None = None) -> list[str]:
        """生成一个覆盖维度的实际值、目标值和配额缺口表格。"""
        lines = ["", f"## {title}", "", "| 项目 | 实际 | 目标 | 缺口 |", "|---|---:|---:|---:|"]
        targets = targets or {}
        for key in sorted(set(str(item) for item in counts) | set(str(item) for item in targets)):
            actual = int(counts.get(key, 0) or 0)
            target = int(targets.get(key, 0) or 0)
            shortage = max(0, target - actual)
            lines.append(f"| {key} | {actual} | {target} | {shortage} |")
        if len(lines) == 5:
            lines.append("| 无 | 0 | 0 | 0 |")
        return lines

    status = "incomplete" if coverage.get("incomplete") else "complete"
    lines = [
        "# 法律题集覆盖报告", "",
        f"- 总题量：{coverage.get('total_count', 0)}",
        f"- 目标题量：{coverage.get('target_total', 0)}",
        f"- 状态：{status}",
    ]
    lines.extend(table_section("维度", coverage.get("dimension_counts", {}), coverage.get("dimension_quotas", {})))
    lines.extend(table_section("题型", coverage.get("question_format_counts", {}), coverage.get("question_format_quotas", {})))
    lines.extend(table_section("难度", coverage.get("difficulty_counts", {}), coverage.get("difficulty_quotas", {})))
    lines.extend(table_section("风险", coverage.get("risk_counts", {}), coverage.get("risk_quotas", {})))
    lines.extend(table_section("案件类别", coverage.get("category_counts", {}), coverage.get("case_type_minimums", {})))
    lines.extend(table_section("Split", coverage.get("split_counts", {}), coverage.get("split_targets", {})))

    lines.extend(["", "## 维度 × 题型矩阵", "", "| 维度 | 题型 | 实际 | 目标 | 缺口 |", "|---|---|---:|---:|---:|"])
    matrix = coverage.get("dimension_format_counts", {})
    matrix_targets = coverage.get("dimension_format_quotas", {})
    matrix_keys = {(str(dim), str(fmt)) for dim, values in matrix.items() for fmt in values}
    matrix_keys.update((str(dim), str(fmt)) for dim, values in matrix_targets.items() for fmt in values)
    if matrix_keys:
        for dim, fmt in sorted(matrix_keys):
            actual = int(matrix.get(dim, {}).get(fmt, 0) or 0)
            target = int(matrix_targets.get(dim, {}).get(fmt, 0) or 0)
            lines.append(f"| {dim} | {fmt} | {actual} | {target} | {max(0, target - actual)} |")
    else:
        lines.append("| 无 | 无 | 0 | 0 | 0 |")

    lines.extend(["", "## 专项标签", ""])
    tag_targets = coverage.get("tag_minimums", {})
    for key in sorted(set(coverage.get("tag_counts", {})) | set(tag_targets)):
        actual = int(coverage.get("tag_counts", {}).get(key, 0) or 0)
        target = int(tag_targets.get(key, 0) or 0)
        lines.append(f"- {key}：实际 {actual}，最低 {target}，缺口 {max(0, target - actual)}")
    if not tag_targets and not coverage.get("tag_counts"):
        lines.append("- 无")

    lines.extend(["", "## 配额缺口", ""])
    shortages = coverage.get("quota_shortages", {})
    lines.extend([f"- {key}：缺 {value}" for key, value in sorted(shortages.items())] or ["- 无"])
    case_shortages = coverage.get("case_type_shortages", {})
    split_shortages = coverage.get("split_shortages", {})
    lines.extend(["", "## 案件类别缺口", ""])
    lines.extend([f"- {key}：缺 {value}" for key, value in sorted(case_shortages.items())] or ["- 无"])
    lines.extend(["", "## Split 缺口", ""])
    lines.extend([f"- {key}：缺 {value}" for key, value in sorted(split_shortages.items())] or ["- 无"])
    lines.extend(["", f"## 被拒候选题：{len(rejected)}", ""])
    for row in rejected[:100]:
        lines.append(f"- {row.get('question_id', row.get('question', ''))}：{row.get('reason', '')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(input_path: str | Path, output_path: str | Path, manifest_path: str | Path,
        max_items: int | None = None, include_pending: bool = False, blueprint_path: str | Path | None = None,
        catalog_path: str | Path | None = None) -> list[dict[str, Any]]:
    """运行题集组装并写出 release、拒绝记录、manifest、coverage 和 metadata。"""
    drafts = read_jsonl(input_path); catalog = load_dimension_catalog(catalog_path); blueprint = load_blueprint(blueprint_path, catalog)
    questions, rejected, coverage = build_release(drafts, include_pending, max_items, blueprint, catalog)
    output = Path(output_path); output.parent.mkdir(parents=True, exist_ok=True); write_jsonl(output, questions)
    rejected_path = Path(str(output) + ".rejected.jsonl"); write_jsonl(rejected_path, rejected)
    coverage_path = output.with_name(output.stem + "_coverage.md"); _write_coverage_report(coverage_path, coverage, rejected)
    target_manifest = Path(manifest_path); target_manifest.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(output.read_bytes()).hexdigest(); case_ids = {str(row.get("case_id")) for row in questions}
    manifest = {"release_version": "1.0.0", "taxonomy_version": load_taxonomy()["version"], "question_count": len(questions), "case_count": len(case_ids), "split_counts": dict(Counter(str(row.get("split")) for row in questions)), **coverage, "sha256": digest, "source": str(input_path), "blueprint": str(blueprint_path or DEFAULT_BLUEPRINT_PATH), "raw_data_included": False}
    target_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = new_run_metadata("legal_benchmark.dataset_build", input=str(input_path), output=str(output), manifest_output=str(target_manifest), rejected_output=str(rejected_path), coverage_report=str(coverage_path), questions=len(questions), cases=len(case_ids), rejected=len(rejected), incomplete=coverage["incomplete"], dimension_counts=coverage["dimension_counts"], question_format_counts=coverage["question_format_counts"], quota_shortages=coverage["quota_shortages"], method="rules+dimension_format_blueprint", model="")
    metadata.update({
        "split_counts": coverage.get("split_counts", {}),
        "split_targets": coverage.get("split_targets", {}),
        "case_type_counts": coverage.get("category_counts", {}),
        "case_type_shortages": coverage.get("case_type_shortages", {}),
        "split_shortages": coverage.get("split_shortages", {}),
        "dimension_format_counts": coverage.get("dimension_format_counts", {}),
        "difficulty_counts": coverage.get("difficulty_counts", {}),
        "risk_counts": coverage.get("risk_counts", {}),
        "tag_counts": coverage.get("tag_counts", {}),
        "quota_satisfied": coverage.get("quota_satisfied", False),
    })
    output.with_suffix(output.suffix + ".metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return questions


def main() -> None:
    """解析题集组装 CLI 参数。"""
    parser = argparse.ArgumentParser(description="按法律维度×题型蓝图组装正式题集")
    parser.add_argument("--input", required=True, help="候选题 JSONL")
    parser.add_argument("--output", required=True, help="正式题集 JSONL")
    parser.add_argument("--manifest-output", required=True, help="发布清单 JSON")
    parser.add_argument("--blueprint", default=None, help="题集蓝图 JSON")
    parser.add_argument("--dimension-catalog", default=None, help="维度目录 JSON")
    parser.add_argument("--max-items", type=int, default=None, help="最多组装题目数")
    parser.add_argument("--include-pending", action="store_true", help="开发试跑时允许 pending 候选题")
    args = parser.parse_args()
    try:
        rows = run(args.input, args.output, args.manifest_output, args.max_items, args.include_pending, args.blueprint, args.dimension_catalog)
        print(f"完成：{args.output}，共 {len(rows)} 题")
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr); raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
