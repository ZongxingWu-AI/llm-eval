"""法律正式题集组装模块。

候选题先经过字段、taxonomy、维度契约与人工审核状态校验，再依据题集蓝图按维度
配额组装 release。配额不足不会静默忽略：覆盖缺口会写入 manifest 和 metadata；超过
配额的候选题会进入 rejected 文件。案件级 split 仍由 split.assign_case_splits 统一分配。
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
from typing import Any

from core.data_io import read_jsonl, write_jsonl
from core.run_metadata import new_run_metadata
from .split import assign_case_splits

_taxonomy = importlib.import_module("methodology.01_造Benchmark.legal.taxonomy")
allowed_values = _taxonomy.allowed_values
load_taxonomy = _taxonomy.load_taxonomy
validate_cause_path = _taxonomy.validate_cause_path

CONFIG_ROOT = Path(__file__).resolve().parents[1] / "config"
DEFAULT_CATALOG_PATH = CONFIG_ROOT / "dimension_catalog.json"
DEFAULT_BLUEPRINT_PATH = CONFIG_ROOT / "dataset_blueprint.json"

REQUIRED_FIELDS = (
    "case_id", "dimension_id", "context_type", "context", "primary_issue", "task_type",
    "reasoning_capabilities", "answer_type", "scoring_method", "difficulty", "risk_level",
    "question", "reference_answer", "rubric", "source_evidence", "case_classification",
)


def _read_json(path: str | Path) -> dict[str, Any]:
    """执行法律题集流程辅助操作。"""
    target = Path(path)
    return json.loads(target.read_text(encoding="utf-8"))


def load_dimension_catalog(path: str | Path | None = None) -> dict[str, Any]:
    """读取维度配置，并拒绝重复或缺失的 dimension_id。"""
    catalog = _read_json(path or DEFAULT_CATALOG_PATH)
    dimensions = catalog.get("dimensions", [])
    if not isinstance(dimensions, list) or not dimensions:
        raise ValueError("dimension_catalog 必须包含非空 dimensions 数组")
    ids: list[str] = []
    for item in dimensions:
        if not isinstance(item, dict) or not str(item.get("dimension_id", "")).strip():
            raise ValueError("dimension_catalog 中存在缺失 dimension_id 的维度")
        ids.append(str(item["dimension_id"]))
    duplicates = sorted(value for value, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"dimension_id 重复：{duplicates}")
    return catalog


def _dimension_map(catalog: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """执行法律题集流程辅助操作。"""
    source = catalog or load_dimension_catalog()
    return {str(item["dimension_id"]): item for item in source.get("dimensions", [])}


def load_blueprint(path: str | Path | None = None, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    """读取独立蓝图；不存在时由维度配置中的 target_count 生成默认蓝图。"""
    target = Path(path) if path else DEFAULT_BLUEPRINT_PATH
    if target.is_file():
        return _read_json(target)
    source = catalog or load_dimension_catalog()
    embedded = source.get("blueprint")
    if isinstance(embedded, dict):
        return embedded
    quotas = {
        str(item["dimension_id"]): int(item.get("target_count", 0) or 0)
        for item in source.get("dimensions", [])
    }
    return {"version": "1.0.0", "dimension_quotas": quotas}


def _quota_map(blueprint: dict[str, Any] | None) -> dict[str, int]:
    """执行法律题集流程辅助操作。"""
    if not blueprint:
        return {}
    raw = blueprint.get("dimension_quotas", blueprint.get("dimension_targets", blueprint.get("quotas", {})))
    if isinstance(raw, list):
        return {
            str(item.get("dimension_id", "")): int(item.get("target_count", item.get("count", 0)) or 0)
            for item in raw if isinstance(item, dict) and item.get("dimension_id")
        }
    if isinstance(raw, dict):
        result: dict[str, int] = {}
        for key, value in raw.items():
            if isinstance(value, dict):
                value = value.get("target_count", value.get("count", 0))
            result[str(key)] = int(value or 0)
        return result
    return {}


def _allowed_context_types(config: dict[str, Any]) -> set[str]:
    """执行法律题集流程辅助操作。"""
    values = config.get("allowed_context_types", config.get("context_types", []))
    if isinstance(values, str):
        values = [values]
    if not values and config.get("context_type"):
        values = [config["context_type"]]
    if not values and config.get("default_context_type"):
        values = [config["default_context_type"]]
    return {str(value) for value in values}


def _taxonomy_valid(row: dict[str, Any], catalog: dict[str, Any] | None = None) -> bool:
    """验证题目、案件分类以及维度映射均属于受控配置。"""
    classification = row.get("case_classification")
    if not isinstance(classification, dict):
        return False

    for row_field, taxonomy_field in (
        ("task_type", "task_types"), ("answer_type", "answer_types"),
        ("scoring_method", "scoring_methods"), ("difficulty", "difficulties"),
        ("risk_level", "risk_levels"),
    ):
        if row.get(row_field) not in allowed_values(taxonomy_field):
            return False

    capabilities = row.get("reasoning_capabilities", [])
    if not isinstance(capabilities, list) or not capabilities:
        return False
    if any(value not in allowed_values("reasoning_capabilities") for value in capabilities):
        return False

    dimensions = _dimension_map(catalog)
    dimension = dimensions.get(str(row.get("dimension_id", "")))
    if not dimension:
        return False
    if row.get("task_type") != dimension.get("task_type"):
        return False
    context = row.get("context")
    question = row.get("question")
    if context is None or str(context).strip() == "":
        return False
    context_text = context if isinstance(context, str) else json.dumps(context, ensure_ascii=False)
    if str(context_text).strip() == str(question or "").strip():
        return False
    allowed_context = _allowed_context_types(dimension)
    if allowed_context and row.get("context_type") not in allowed_context:
        return False
    recommended_scoring = dimension.get("scoring_methods", dimension.get("scoring_method"))
    if isinstance(recommended_scoring, str):
        recommended_scoring = [recommended_scoring]
    if recommended_scoring and row.get("scoring_method") not in set(recommended_scoring):
        return False

    for case_field, taxonomy_field in (
        ("domain", "domains"), ("procedure_stage", "procedure_stages"),
        ("document_type", "document_types"), ("primary_category", "primary_categories"),
    ):
        if classification.get(case_field) not in allowed_values(taxonomy_field):
            return False
    primary = classification.get("primary_category", "")
    if not validate_cause_path(primary, classification.get("cause_path", [])):
        return False
    if any(value not in allowed_values("procedure_tags") for value in classification.get("procedure_tags", [])):
        return False
    if any(value not in allowed_values("evidence_tags") for value in classification.get("evidence_tags", [])):
        return False
    applicable = dimension.get("applicable_case_types", [])
    if applicable and "*" not in applicable and primary not in applicable:
        return False
    return True


def _accepted_sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    """执行法律题集流程辅助操作。"""
    return str(row.get("dimension_id", "")), str(row.get("case_id", "")), str(row.get("question", ""))


def dimension_coverage(rows: list[dict[str, Any]], blueprint: dict[str, Any] | None = None) -> dict[str, Any]:
    """汇总维度、案件类别、难度和风险覆盖，并显式列出配额缺口。"""
    quota = _quota_map(blueprint)
    dimension_counts = Counter(str(row.get("dimension_id", "未标注")) for row in rows)
    category_counts: Counter[str] = Counter()
    difficulty_counts = Counter(str(row.get("difficulty", "未标注")) for row in rows)
    risk_counts = Counter(str(row.get("risk_level", "未标注")) for row in rows)
    for row in rows:
        classification = row.get("case_classification", {})
        category = classification.get("primary_category", "未分类") if isinstance(classification, dict) else "未分类"
        category_counts[str(category)] += 1
    shortages = {
        dimension_id: target - dimension_counts.get(dimension_id, 0)
        for dimension_id, target in quota.items()
        if target > dimension_counts.get(dimension_id, 0)
    }
    return {
        "dimension_counts": dict(dimension_counts),
        "dimension_quotas": quota,
        "quota_shortages": shortages,
        "quota_satisfied": not shortages,
        "category_counts": dict(category_counts),
        "difficulty_counts": dict(difficulty_counts),
        "risk_counts": dict(risk_counts),
    }


def build_release(
    drafts: list[dict[str, Any]], include_pending: bool = False, max_items: int | None = None,
    blueprint: dict[str, Any] | None = None, catalog: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """按维度配额组装题集，返回题目、拒绝记录和覆盖统计。"""
    catalog = catalog or load_dimension_catalog()
    if blueprint is None:
        blueprint = load_blueprint(catalog=catalog)
    quotas = _quota_map(blueprint)
    valid_by_dimension: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rejected: list[dict[str, Any]] = []

    for draft in drafts:
        if not include_pending and draft.get("review_status") != "approved":
            continue
        missing = [field for field in REQUIRED_FIELDS if not draft.get(field)]
        taxonomy_valid = _taxonomy_valid(draft, catalog)
        if missing or not taxonomy_valid:
            rejected.append({
                "case_id": draft.get("case_id", ""), "dimension_id": draft.get("dimension_id", ""),
                "question": draft.get("question", ""),
                "reason": f"missing={missing}; taxonomy_valid={taxonomy_valid}",
            })
            continue
        valid_by_dimension[str(draft["dimension_id"])].append(dict(draft))

    accepted: list[dict[str, Any]] = []
    dimension_order = list(quotas) or sorted(valid_by_dimension)
    for dimension_id in dimension_order:
        candidates = sorted(valid_by_dimension.pop(dimension_id, []), key=_accepted_sort_key)
        target = quotas.get(dimension_id, len(candidates))
        selected = candidates[:target] if target > 0 else candidates
        extras = candidates[len(selected):]
        accepted.extend(selected)
        for row in extras:
            rejected.append({
                "case_id": row.get("case_id", ""), "dimension_id": dimension_id,
                "question": row.get("question", ""), "reason": f"dimension quota exceeded: {target}",
            })
    for dimension_id in sorted(valid_by_dimension):
        accepted.extend(sorted(valid_by_dimension[dimension_id], key=_accepted_sort_key))

    accepted.sort(key=_accepted_sort_key)
    if max_items is not None and max_items > 0 and len(accepted) > max_items:
        for row in accepted[max_items:]:
            rejected.append({
                "case_id": row.get("case_id", ""), "dimension_id": row.get("dimension_id", ""),
                "question": row.get("question", ""), "reason": f"max_items exceeded: {max_items}",
            })
        accepted = accepted[:max_items]

    counters: Counter[str] = Counter()
    release_date = date.today().isoformat()
    for row in accepted:
        case_id = str(row["case_id"])
        counters[case_id] += 1
        row["question_id"] = f"legal_{case_id.removeprefix('case_')}_{counters[case_id]:02d}"
        row["version"] = "1.0.0"
        row["release_date"] = release_date
    accepted = assign_case_splits(accepted)
    return accepted, rejected, dimension_coverage(accepted, blueprint)


def build(
    drafts: list[dict[str, Any]], include_pending: bool = False, max_items: int | None = None,
    blueprint: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """兼容原接口；详细覆盖数据由 build_release 返回。"""
    accepted, rejected, _ = build_release(drafts, include_pending, max_items, blueprint)
    return accepted, rejected


def run(
    input_path: str | Path, output_path: str | Path, manifest_path: str | Path,
    max_items: int | None = None, include_pending: bool = False,
    blueprint_path: str | Path | None = None, catalog_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """执行法律题集流程辅助操作。"""
    drafts = read_jsonl(input_path)
    catalog = load_dimension_catalog(catalog_path)
    blueprint = load_blueprint(blueprint_path, catalog)
    questions, rejected, coverage = build_release(drafts, include_pending, max_items, blueprint, catalog)
    write_jsonl(output_path, questions)
    rejected_path = Path(str(output_path) + ".rejected.jsonl")
    write_jsonl(rejected_path, rejected)

    output = Path(output_path)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    split_counts = Counter(str(row["split"]) for row in questions)
    case_ids = {str(row["case_id"]) for row in questions}
    taxonomy = load_taxonomy()
    manifest = {
        "release_version": "1.0.0", "taxonomy_version": taxonomy["version"],
        "question_count": len(questions), "case_count": len(case_ids),
        "split_counts": dict(split_counts), **coverage, "sha256": digest,
        "source": str(input_path), "blueprint": str(blueprint_path or DEFAULT_BLUEPRINT_PATH),
        "raw_data_included": False,
    }
    target_manifest = Path(manifest_path)
    target_manifest.parent.mkdir(parents=True, exist_ok=True)
    target_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = new_run_metadata(
        "legal_benchmark.dataset_build", input=str(input_path), output=str(output_path),
        manifest_output=str(manifest_path), rejected_output=str(rejected_path),
        questions=len(questions), cases=len(case_ids), rejected=len(rejected),
        dimension_counts=coverage["dimension_counts"], quota_shortages=coverage["quota_shortages"],
        method="rules+dimension_blueprint", model="",
    )
    output.with_suffix(output.suffix + ".metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return questions


def main() -> None:
    """执行法律题集流程辅助操作。"""
    parser = argparse.ArgumentParser(description="按维度蓝图组装经人工审核的法律正式题集")
    parser.add_argument("--input", required=True, help="候选题 JSONL")
    parser.add_argument("--output", required=True, help="正式题集 JSONL")
    parser.add_argument("--manifest-output", required=True, help="发布清单 JSON")
    parser.add_argument("--blueprint", default=None, help="题集蓝图 JSON；默认使用内置蓝图")
    parser.add_argument("--dimension-catalog", default=None, help="维度配置 JSON；默认使用内置配置")
    parser.add_argument("--max-items", type=int, default=None, help="最多组装前 N 道通过项")
    parser.add_argument("--include-pending", action="store_true", help="仅用于开发试跑；正式发布不要使用")
    args = parser.parse_args()
    try:
        questions = run(
            args.input, args.output, args.manifest_output, args.max_items,
            args.include_pending, args.blueprint, args.dimension_catalog,
        )
        print(f"完成：{args.output}，共 {len(questions)} 题")
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
