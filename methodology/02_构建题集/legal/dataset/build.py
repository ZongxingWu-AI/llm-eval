"""法律正式题集组装模块。

项目位置：法律真实案例评测线的 dataset 构建阶段。
输入：命令行指定的 drafts JSONL 中经过人工审核的候选题。
输出：releases/legal_questions_release_v1.jsonl、拒绝记录、legal_release_manifest_v1.json 和相邻 metadata。
上下游：上游是出题与人工审稿，下游是 validation.validate 和 evaluation.run。
副作用：覆盖指定 release、rejected 和 manifest 文件；不调用模型，不接触 raw 原文。"""

import argparse
import importlib
import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from core.data_io import read_jsonl, write_jsonl
from core.run_metadata import new_run_metadata
from .split import assign_case_splits
_taxonomy = importlib.import_module("methodology.01_造Benchmark.legal.taxonomy")
allowed_values = _taxonomy.allowed_values
load_taxonomy = _taxonomy.load_taxonomy
validate_cause_path = _taxonomy.validate_cause_path

REQUIRED_FIELDS = ("case_id", "primary_issue", "task_type", "reasoning_capabilities", "answer_type",
                   "scoring_method", "difficulty", "risk_level", "question", "reference_answer", "rubric", "source_evidence",
                   "case_classification")


def _taxonomy_valid(row: dict) -> bool:
    """用途：验证候选题的题目级和案件级标签是否全部来自受控 taxonomy。

    输入：row 是 generation 产生的候选题字典。
    输出：所有类型、能力、案由路径和标签合法时返回 True，否则返回 False。
    运行前数据形态：运行前候选题可能含模型自由生成标签。
    运行后数据变化：运行后得到布尔判定，build 据此接收或拒绝题目。
    副作用：读取 taxonomy 缓存，不修改 row、不写文件、不调用模型。
    异常或失败处理：字段类型错误、未知标签或不连续 cause_path 都返回 False。"""

    classification = row.get("case_classification")
    if not isinstance(classification, dict):
        return False

    controlled_question_fields = (
        ("task_type", "task_types"),
        ("answer_type", "answer_types"),
        ("scoring_method", "scoring_methods"),
        ("difficulty", "difficulties"),
        ("risk_level", "risk_levels"),
    )
    for row_field, taxonomy_field in controlled_question_fields:
        value = row.get(row_field)
        if value not in allowed_values(taxonomy_field):
            return False

    reasoning_capabilities = row.get("reasoning_capabilities", [])
    if not isinstance(reasoning_capabilities, list):
        return False
    allowed_reasoning = allowed_values("reasoning_capabilities")
    for capability in reasoning_capabilities:
        if capability not in allowed_reasoning:
            return False

    controlled_case_fields = (
        ("domain", "domains"),
        ("procedure_stage", "procedure_stages"),
        ("document_type", "document_types"),
        ("primary_category", "primary_categories"),
    )
    for case_field, taxonomy_field in controlled_case_fields:
        value = classification.get(case_field)
        if value not in allowed_values(taxonomy_field):
            return False

    primary_category = classification.get("primary_category", "")
    cause_path = classification.get("cause_path", [])
    if not isinstance(cause_path, list):
        return False
    if not validate_cause_path(primary_category, cause_path):
        return False

    procedure_tags = classification.get("procedure_tags", [])
    if not isinstance(procedure_tags, list):
        return False
    allowed_procedure_tags = allowed_values("procedure_tags")
    for tag in procedure_tags:
        if tag not in allowed_procedure_tags:
            return False

    evidence_tags = classification.get("evidence_tags", [])
    if not isinstance(evidence_tags, list):
        return False
    allowed_evidence_tags = allowed_values("evidence_tags")
    for tag in evidence_tags:
        if tag not in allowed_evidence_tags:
            return False

    return True


def _accepted_sort_key(row: dict) -> tuple[str, str]:
    """用途：为已接收候选题生成稳定的案件和题目排序键。

    输入：row 是通过字段与 taxonomy 校验的题目。
    输出：返回 (case_id, question) 字符串元组。
    运行前数据形态：accepted 仍保留输入顺序。
    运行后数据变化：排序后同案题集中排列，重复运行顺序稳定。
    副作用：只读字典，不写文件、不调用模型。
    异常或失败处理：字段缺失时用空字符串，确保排序仍可执行。"""
    case_id = str(row.get("case_id", ""))
    question = str(row.get("question", ""))
    return case_id, question


def build(drafts: list[dict], include_pending: bool = False, max_items: int | None = None) -> tuple[list[dict], list[dict]]:
    """用途：审核候选题必填字段、状态、taxonomy 和证据后，分配正式题号与案件级 split。

    输入：drafts 是候选题列表；include_pending 控制开发试跑；max_items 限制接收数量。
    输出：返回 (正式题目列表, 拒绝记录列表)。
    运行前数据形态：运行前题目可能为 pending、无 question_id 或含非法标签。
    运行后数据变化：运行后 accepted 获得稳定 question_id、dataset_version 和 split；同一 case_id 的题不会跨集合。
    副作用：读取 taxonomy；只处理内存，不写文件、不调用模型。
    异常或失败处理：缺字段、未获批准、标签非法或证据为空时记录明确 reject reason，不中断其他题。
    最小示例：十个同类案件按固定规则分为 3 个 dev、2 个 calibration、5 个 test。"""

    accepted: list[dict] = []
    rejected: list[dict] = []
    for draft in drafts:
        if not include_pending and draft.get("review_status") != "approved":
            continue
        missing: list[str] = []
        for field in REQUIRED_FIELDS:
            if not draft.get(field):
                missing.append(field)
        taxonomy_valid = _taxonomy_valid(draft)
        if missing or not taxonomy_valid:
            rejected.append({
                "case_id": draft.get("case_id", ""),
                "question": draft.get("question", ""),
                "reason": f"missing={missing}; taxonomy_valid={taxonomy_valid}",
            })
            continue
        accepted.append(dict(draft))
        reached_limit = max_items is not None and max_items > 0 and len(accepted) >= max_items
        if reached_limit:
            break

    accepted.sort(key=_accepted_sort_key)
    counters: Counter[str] = Counter()
    release_date = date.today().isoformat()
    for row in accepted:
        case_id = row["case_id"]
        counters[case_id] += 1
        number = counters[case_id]
        short_case_id = case_id.removeprefix("case_")
        row["question_id"] = f"legal_{short_case_id}_{number:02d}"
        row["version"] = "1.0.0"
        row["release_date"] = release_date
    return assign_case_splits(accepted), rejected


def run(input_path: str | Path, output_path: str | Path, manifest_path: str | Path,
        max_items: int | None = None, include_pending: bool = False) -> list[dict]:
    """用途：从 drafts JSONL 组装正式 release，并写拒绝记录和发布清单。

    输入：input_path、output_path、manifest_output、max_items、include_pending 控制本次构建。
    输出：返回正式题目列表；写指定 release、rejected JSONL、发布清单和相邻 metadata。
    运行前数据形态：运行前是一行一道候选题。
    运行后数据变化：运行后通过项进入 release，拒绝项单独留痕，manifest 汇总版本、哈希、split 和分类数量。
    副作用：读取候选题，创建父目录并覆盖发布文件；不调用模型、不修改 raw 或 extract 数据。
    异常或失败处理：输入不存在或写入失败时抛出；单题质量问题进入 rejected 文件。"""

    drafts = read_jsonl(input_path)
    questions, rejected = build(drafts, include_pending, max_items)
    write_jsonl(output_path, questions)
    rejected_path = Path(output_path).with_suffix(".rejected.jsonl")
    write_jsonl(rejected_path, rejected)

    output = Path(output_path)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    split_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    case_ids: set[str] = set()
    for row in questions:
        split_counts[row["split"]] += 1
        classification = row.get("case_classification", {})
        if not isinstance(classification, dict):
            classification = {}
        category = classification.get("primary_category", "未分类")
        category_counts[category] += 1
        case_ids.add(row["case_id"])

    taxonomy = load_taxonomy()
    manifest = {
        "release_version": "1.0.0",
        "taxonomy_version": taxonomy["version"],
        "question_count": len(questions),
        "case_count": len(case_ids),
        "split_counts": dict(split_counts),
        "category_counts": dict(category_counts),
        "sha256": digest,
        "source": str(input_path),
        "raw_data_included": False,
    }
    target_manifest = Path(manifest_path)
    target_manifest.parent.mkdir(parents=True, exist_ok=True)
    target_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = new_run_metadata(
        "legal_benchmark.dataset_build",
        input=str(input_path),
        output=str(output_path),
        manifest_output=str(manifest_path),
        rejected_output=str(rejected_path),
        questions=len(questions),
        cases=len(case_ids),
        rejected=len(rejected),
        method="rules",
        model="",
    )
    output.with_suffix(output.suffix + ".metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return questions


def main() -> None:
    """用途：提供题集组装 CLI，把路径、数量和 --include-pending 传给 run。

    输入：参数来自 argparse；默认读取 drafts 并写 releases 和 manifests。
    输出：成功打印正式题数；失败打印错误并以状态码 1 退出。
    运行前数据形态：运行前是候选题和命令行参数。
    运行后数据变化：运行后得到可供 validation 使用的正式题集。
    副作用：创建目录并覆盖 release、rejected 和 manifest；不调用模型。
    异常或失败处理：参数错误由 argparse 处理；run 异常转换为非零退出。"""

    parser = argparse.ArgumentParser(description="组装经人工审核的法律正式题集")
    parser.add_argument("--input", required=True, help="候选题 JSONL")
    parser.add_argument("--output", required=True, help="正式题集 JSONL")
    parser.add_argument("--manifest-output", required=True, help="发布清单 JSON")
    parser.add_argument("--max-items", type=int, default=None, help="最多组装前 N 道通过项")
    parser.add_argument("--include-pending", action="store_true", help="仅用于开发试跑；正式发布不要使用")
    args = parser.parse_args()
    try:
        questions = run(args.input, args.output, args.manifest_output, args.max_items, args.include_pending)
        print(f"完成：{args.output}，共 {len(questions)} 题")
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
