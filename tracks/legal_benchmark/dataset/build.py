"""项目模块：tracks/legal_benchmark/dataset/build.py。

本文件属于三条评测线或公共工具层的一部分，负责完成本文件名对应的处理步骤。输入来自上游函数或数据目录，输出返回给下游函数或写入对应结果目录。

项目位置：tracks/legal_benchmark/dataset/build.py。
主要用途：法律真实案例 Benchmark，负责判决书解析、结构化提取、出题、校验和法律评测。
输入：输入来自法律线 data/raw、parsed、cleaned、drafts、releases 或 taxonomy/schema。
输出：输出按生命周期写入法律线对应 data 子目录或 results 目录。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：ingestion/extraction/generation/evaluation 可能写文件；只有带模型选项时才调用模型。
"""

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from core.data_io import read_jsonl, write_jsonl
from tracks.legal_benchmark.dataset.split import assign_case_splits
from tracks.legal_benchmark.paths import DATA_ROOT
from tracks.legal_benchmark.taxonomy import allowed_values, load_taxonomy, validate_cause_path

REQUIRED_FIELDS = ("case_id", "primary_issue", "task_type", "reasoning_capabilities", "answer_type",
                   "scoring_method", "difficulty", "risk_level", "question", "reference_answer", "rubric", "source_evidence",
                   "case_classification")


def _taxonomy_valid(row: dict) -> bool:
    """为同一文件中的公开流程提供一个小而明确的辅助步骤。

参数：row。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    classification = row.get("case_classification")
    if not isinstance(classification, dict):
        return False
    primary_category = classification.get("primary_category", "")
    cause_path = classification.get("cause_path", [])
    return (row.get("task_type") in allowed_values("task_types")
            and row.get("answer_type") in allowed_values("answer_types")
            and row.get("scoring_method") in allowed_values("scoring_methods")
            and row.get("difficulty") in allowed_values("difficulties")
            and row.get("risk_level") in allowed_values("risk_levels")
            and all(value in allowed_values("reasoning_capabilities") for value in row.get("reasoning_capabilities", []))
            and classification.get("domain") in allowed_values("domains")
            and classification.get("procedure_stage") in allowed_values("procedure_stages")
            and classification.get("document_type") in allowed_values("document_types")
            and primary_category in allowed_values("primary_categories")
            and validate_cause_path(primary_category, cause_path)
            and all(value in allowed_values("procedure_tags") for value in classification.get("procedure_tags", []))
            and all(value in allowed_values("evidence_tags") for value in classification.get("evidence_tags", [])))


def build(drafts: list[dict], include_pending: bool = False, max_items: int | None = None) -> tuple[list[dict], list[dict]]:
    """从候选题组装正式题集，并补充题号和案件级 split。

    输入是 generation 阶段产生的草稿；默认只接受 ``review_status=approved``。
    输出是“正式题列表 + 被拒绝记录列表”，被拒绝记录会写入单独 JSONL，便于
    人工修订后重跑。函数不调用模型，正式题随后由 validation 和 evaluation 使用。
    """

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


def run(input_path: str | Path = DATA_ROOT / "drafts" / "candidate_questions.jsonl",
        output_path: str | Path = DATA_ROOT / "releases" / "legal_questions.jsonl",
        manifest_path: str | Path = DATA_ROOT / "manifests" / "release_manifest.json",
        max_items: int | None = None, include_pending: bool = False) -> list[dict]:
    """完成当前模块中的一个处理步骤。

参数：input_path、output_path、manifest_path、max_items、include_pending。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

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
    return questions


def main() -> None:
    """完成当前模块中的一个处理步骤。

参数：无。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    parser = argparse.ArgumentParser(description="组装经人工审核的法律正式题集")
    parser.add_argument("--input", default=str(DATA_ROOT / "drafts" / "candidate_questions.jsonl"), help="候选题 JSONL")
    parser.add_argument("--output", default=str(DATA_ROOT / "releases" / "legal_questions.jsonl"), help="正式题集 JSONL")
    parser.add_argument("--manifest-output", default=str(DATA_ROOT / "manifests" / "release_manifest.json"), help="发布清单 JSON")
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


