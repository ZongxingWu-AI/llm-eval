"""法律多维度题集配置加载器。

输入：默认读取同目录的 ``dimension_catalog.json``，也可显式传入 JSON 路径。
输出：经过结构校验的维度目录，以及按 dimension_id 获取的单一维度配置。
上下游：generation、dataset.build 和 validation 共享本模块，避免分别维护维度标签。
副作用：只读本地 JSON；不调用模型、不写文件。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


DIMENSION_CATALOG_PATH = Path(__file__).resolve().with_name("dimension_catalog.json")
_DIMENSION_FIELDS = {
    "dimension_id",
    "task_type",
    "reasoning_capabilities",
    "applicable_case_types",
    "target_count",
    "context_types",
    "default_context_type",
    "scoring_method",
    "prompt_template",
    "required_answer_points",
    "difficulty_distribution",
    "risk_distribution",
}
_CONTEXT_TYPES = {"source_excerpt", "full_document", "self_contained", "scenario"}
_SCORING_METHODS = {"rule", "redline", "rubric_judge"}
_DIFFICULTIES = {"easy", "medium", "hard"}
_RISK_LEVELS = {"low", "medium", "high"}
_EXPECTED_DIMENSION_COUNT = 9


def _validate_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    '''校验九类法律评测维度、上下文策略、配额和评分配置。'''
    if not isinstance(catalog, dict):
        raise ValueError("dimension catalog must be a JSON object")
    dimensions = catalog.get("dimensions")
    if not isinstance(dimensions, list):
        raise ValueError("dimension catalog must contain a dimensions array")
    if len(dimensions) != _EXPECTED_DIMENSION_COUNT:
        raise ValueError(f"dimension catalog must contain {_EXPECTED_DIMENSION_COUNT} dimensions")

    ids: list[str] = []
    for dimension in dimensions:
        if not isinstance(dimension, dict):
            raise ValueError("each dimension must be a JSON object")
        missing = sorted(_DIMENSION_FIELDS - set(dimension))
        if missing:
            raise ValueError(f"dimension is missing fields: {', '.join(missing)}")
        dimension_id = dimension["dimension_id"]
        if not isinstance(dimension_id, str) or not dimension_id.strip():
            raise ValueError("dimension_id must be a non-empty string")
        ids.append(dimension_id)
        if not isinstance(dimension["task_type"], str) or not dimension["task_type"].strip():
            raise ValueError(f"{dimension_id}: task_type must be a non-empty string")
        if not isinstance(dimension["reasoning_capabilities"], list) or not dimension["reasoning_capabilities"]:
            raise ValueError(f"{dimension_id}: reasoning_capabilities must be a non-empty array")
        if not isinstance(dimension["applicable_case_types"], list) or not dimension["applicable_case_types"]:
            raise ValueError(f"{dimension_id}: applicable_case_types must be a non-empty array")
        if not isinstance(dimension["target_count"], int) or dimension["target_count"] <= 0:
            raise ValueError(f"{dimension_id}: target_count must be a positive integer")
        context_types = dimension["context_types"]
        if not isinstance(context_types, list) or not context_types or not set(context_types) <= _CONTEXT_TYPES:
            raise ValueError(f"{dimension_id}: context_types contains an unsupported value")
        if dimension["default_context_type"] not in context_types:
            raise ValueError(f"{dimension_id}: default_context_type must be listed in context_types")
        if dimension["scoring_method"] not in _SCORING_METHODS:
            raise ValueError(f"{dimension_id}: unsupported scoring_method")
        if not isinstance(dimension["prompt_template"], str) or not dimension["prompt_template"].strip():
            raise ValueError(f"{dimension_id}: prompt_template must be a non-empty string")
        if not isinstance(dimension["required_answer_points"], list) or not dimension["required_answer_points"]:
            raise ValueError(f"{dimension_id}: required_answer_points must be a non-empty array")
        for field, allowed in (("difficulty_distribution", _DIFFICULTIES), ("risk_distribution", _RISK_LEVELS)):
            distribution = dimension[field]
            if not isinstance(distribution, dict) or set(distribution) != allowed:
                raise ValueError(f"{dimension_id}: {field} must contain exactly {sorted(allowed)}")
            if any(not isinstance(value, (int, float)) or value < 0 for value in distribution.values()):
                raise ValueError(f"{dimension_id}: {field} values must be non-negative numbers")
            if abs(sum(distribution.values()) - 1.0) > 1e-9:
                raise ValueError(f"{dimension_id}: {field} must sum to 1.0")

    if len(ids) != len(set(ids)):
        raise ValueError("dimension_id values must be unique")
    blueprint = catalog.get("blueprint")
    if blueprint is not None:
        if not isinstance(blueprint, dict):
            raise ValueError("blueprint must be a JSON object when provided")
        targets = blueprint.get("dimension_targets")
        if targets is not None:
            expected_targets = {item["dimension_id"]: item["target_count"] for item in dimensions}
            if targets != expected_targets:
                raise ValueError("blueprint.dimension_targets must match dimension target_count values")
    return catalog


@lru_cache(maxsize=1)
def _load_default_catalog() -> dict[str, Any]:
    """读取默认的法律维度目录配置。"""
    return _load_catalog_from_path(DIMENSION_CATALOG_PATH)


def _load_catalog_from_path(path: Path) -> dict[str, Any]:
    """读取指定路径的维度目录并执行结构校验。"""
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"dimension catalog not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid dimension catalog JSON: {path}") from exc
    return _validate_catalog(catalog)


def load_dimension_catalog(path: str | Path | None = None) -> dict[str, Any]:
    """读取并校验维度目录；不传路径时读取仓库内置目录。"""

    if path is None:
        return _load_default_catalog()
    return _load_catalog_from_path(Path(path))


def get_dimension(dimension_id: str, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    """按唯一 dimension_id 获取维度配置，未知 ID 明确抛出 KeyError。"""

    active_catalog = load_dimension_catalog() if catalog is None else _validate_catalog(catalog)
    for dimension in active_catalog["dimensions"]:
        if dimension["dimension_id"] == dimension_id:
            return dimension
    raise KeyError(f"unknown legal dimension_id: {dimension_id}")


__all__ = ["DIMENSION_CATALOG_PATH", "get_dimension", "load_dimension_catalog"]
