"""法律 Benchmark 的独立结果评测入口。

本阶段读取正式 release 和 03 保存的原始回答，按 question_id 一一配对，使用 release 中的
题面、参考答案、rubric 和 scoring_method 调用既有单题评分器。更换裁判模型、评分 Prompt
或评分逻辑时，只需重新运行本阶段，不会再次调用被测模型。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import llm_client
from core.data_io import read_jsonl, write_jsonl
from core.project_paths import LEGAL_RESULTS_ROOT as RESULTS_ROOT
from core.run_metadata import new_run_metadata, timestamped_run_dir

from . import legal_scorer
from .excel_export import export_jsonl


def _validate_ids(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    """校验输入记录的 question_id 非空且唯一，并返回按 ID 索引的记录。"""
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        question_id = str(row.get("question_id") or "").strip()
        if not question_id:
            raise ValueError(f"{label}中存在缺失 question_id")
        if question_id in indexed:
            raise ValueError(f"{label}中存在重复 question_id：{question_id}")
        indexed[question_id] = row
    return indexed


def _sha256(path: Path) -> str:
    """计算正式 release 的 SHA-256，确保评分使用的题集版本可追踪。"""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _case_category(question: dict[str, Any]) -> str:
    """从正式 release 提取案件类别，不信任 03 原始回答中的副本。"""
    classification = question.get("case_classification")
    if isinstance(classification, dict):
        for key in ("primary_category", "case_category", "category", "domain"):
            value = classification.get(key)
            if value:
                return str(value)
    return str(question.get("case_category") or question.get("domain") or "")


def _base_result(question: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    """只从正式题集和原始回答合并结果字段，避免信任回答文件中的题目文本。"""
    return {
        "question_id": question.get("question_id", ""),
        "case_id": question.get("case_id", ""),
        "split": question.get("split", ""),
        "primary_issue": question.get("primary_issue", ""),
        "dimension_id": question.get("dimension_id", ""),
        "task_type": question.get("task_type", ""),
        "context_type": question.get("context_type", ""),
        "case_category": _case_category(question),
        "difficulty": question.get("difficulty", ""),
        "risk_level": question.get("risk_level", ""),
        "question": question.get("question", ""),
        "model_answer": output.get("model_answer", ""),
        "reference_answer": question.get("reference_answer", ""),
        "scoring_method": question.get("scoring_method", ""),
        "latency_seconds": output.get("latency_seconds", ""),
        "total_tokens": output.get("total_tokens", ""),
        "finish_reason": output.get("finish_reason", ""),
    }


def _scoring_error_message(scoring: Any) -> str | None:
    """识别评分器返回的可结构化失败，兼容现有 Rubric Judge 解析失败口径。"""
    if not isinstance(scoring, dict):
        return "评分器返回了非对象结果"
    if scoring.get("judge_reason") == "裁判输出无法解析":
        return "裁判输出无法解析"
    if scoring.get("reason") == "裁判解析失败":
        return "裁判输出无法解析"
    return None


def score_outputs(
    questions: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    judge_client: Any = None,
    judge_model: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """依据正式 release 对已保存的原始回答逐题评分。

    输入：正式题目列表、03 生成的原始回答列表，以及可选 JUDGE 客户端和模型名。
    输出：评分结果列表与错误列表；评分失败的结果仍保留 model_answer 和调用元数据。
    关联规则：两边必须按 question_id 完整一一匹配；评分只使用正式题集字段，不信任回答副本。
    副作用：仅 rubric_judge 会调用 judge_client；rule 和 redline 完全不调用模型。
    """
    question_by_id = _validate_ids(questions, "正式题集")
    output_by_id = _validate_ids(outputs, "原始回答")
    question_ids = set(question_by_id)
    output_ids = set(output_by_id)
    missing = sorted(question_ids - output_ids)
    extra = sorted(output_ids - question_ids)
    if missing or extra:
        mismatch_parts: list[str] = []
        if missing:
            mismatch_parts.append("缺失 question_id：" + ", ".join(missing))
        if extra:
            mismatch_parts.append("无法匹配的 question_id：" + ", ".join(extra))
        raise ValueError("；".join(mismatch_parts))

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, question in enumerate(questions, start=1):
        question_id = str(question["question_id"])
        output = output_by_id[question_id]
        print(f"[法律结果评测] {index}/{len(questions)} {question_id} ...", end=" ", flush=True)
        result = _base_result(question, output)
        try:
            scoring = legal_scorer.score_one(
                question,
                str(output.get("model_answer") or ""),
                judge_client,
                judge_model,
            )
            failure = _scoring_error_message(scoring)
            if failure:
                raise RuntimeError(failure)
            result.update({
                "verdict": scoring.get("verdict", ""),
                "reason": scoring.get("reason", ""),
                "scoring_details": scoring,
                "scoring_status": "ok",
            })
            results.append(result)
            print(result["verdict"])
        except Exception as exc:
            reason = str(exc)
            result.update({
                "verdict": "",
                "reason": reason,
                "scoring_details": {},
                "scoring_status": "error",
            })
            results.append(result)
            errors.append({
                "question_id": question_id,
                "case_id": question.get("case_id", ""),
                "dimension_id": question.get("dimension_id", ""),
                "task_type": question.get("task_type", ""),
                "context_type": question.get("context_type", ""),
                "case_category": _case_category(question),
                "difficulty": question.get("difficulty", ""),
                "risk_level": question.get("risk_level", ""),
                "model_answer": output.get("model_answer", ""),
                "error": reason,
            })
            print(f"ERROR: {reason}")
    return results, errors


def _counts_by(results: list[dict[str, Any]], field: str) -> dict[str, Counter]:
    """按指定维度汇总 PASS、REVIEW、REJECT 与 ERROR。"""
    grouped: dict[str, Counter] = defaultdict(Counter)
    for row in results:
        label = str(row.get(field) or "未分类")
        verdict = str(row.get("verdict") or "ERROR")
        grouped[label][verdict] += 1
    return grouped


def _format_counts(counts: Counter) -> str:
    """格式化一组结果计数，并显式给出错误率。"""
    total = sum(counts.values())
    error_rate = (counts["ERROR"] / total * 100) if total else 0
    return (
        f"题量 {total}：PASS {counts['PASS']} / REVIEW {counts['REVIEW']} / "
        f"REJECT {counts['REJECT']} / ERROR {counts['ERROR']}；错误率 {error_rate:.1f}%"
    )


def _append_group_section(
    lines: list[str],
    results: list[dict[str, Any]],
    title: str,
    field: str,
) -> None:
    """向报告追加一个按 release 字段分组的统计章节。"""
    lines.extend(["", f"## {title}", ""])
    grouped = _counts_by(results, field)
    if not grouped:
        lines.append("- 无结果")
        return
    for label, counts in sorted(grouped.items()):
        lines.append(f"- {label}：{_format_counts(counts)}")


def build_report(results: list[dict[str, Any]]) -> str:
    """生成总体、分维度和分元数据的 Markdown 评测报告。"""
    total_counts: Counter[str] = Counter(str(row.get("verdict") or "ERROR") for row in results)
    lines = [
        "# 法律真实案例 Benchmark 结果评测报告", "",
        f"- 题量：{len(results)}",
        f"- PASS：{total_counts['PASS']} / REVIEW：{total_counts['REVIEW']} / REJECT：{total_counts['REJECT']} / ERROR：{total_counts['ERROR']}",
        "", "## 每题结果", "",
        "| 题号 | dimension_id | context_type | split | 案件类别 | 任务类型 | 难度 | 风险 | 评分方式 | 结论 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in results:
        cells = [
            row.get("question_id", ""), row.get("dimension_id", ""), row.get("context_type", ""), row.get("split", ""),
            row.get("case_category", ""), row.get("task_type", ""), row.get("difficulty", ""),
            row.get("risk_level", ""), row.get("scoring_method", ""), row.get("verdict", "") or "ERROR",
        ]
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in cells) + " |")

    for title, field in (
        ("按 split 统计", "split"),
        ("按任务类型统计", "task_type"),
        ("按 dimension_id 统计", "dimension_id"),
        ("按案件类别统计", "case_category"),
        ("按难度统计", "difficulty"),
        ("按风险等级统计", "risk_level"),
    ):
        _append_group_section(lines, results, title, field)

    lines.extend(["", "## 人工复核清单", ""])
    review_rows = [row for row in results if str(row.get("verdict") or "ERROR") in {"REVIEW", "ERROR"}]
    if not review_rows:
        lines.append("- 无待人工复核题目")
    else:
        lines.extend([
            "| 题号 | dimension_id | 案件类别 | 结论 | 原因 |",
            "|---|---|---|---|---|",
        ])
        for row in review_rows:
            cells = [
                row.get("question_id", ""), row.get("dimension_id", ""),
                row.get("case_category", ""), row.get("verdict", "") or "ERROR", row.get("reason", ""),
            ]
            lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in cells) + " |")
    return "\n".join(lines) + "\n"

def _build_judge_client(questions: list[dict[str, Any]]) -> tuple[Any, str | None]:
    """仅当正式题集包含 rubric_judge 时创建 JUDGE 客户端。"""
    if not any(row.get("scoring_method") == "rubric_judge" for row in questions):
        return None, None
    llm_client.load_env()
    base, key, model = llm_client.read_role("JUDGE", "deepseek-v4-flash")
    return llm_client.build_client(base, key), model


def run(
    questions_path: str | Path,
    outputs_path: str | Path,
    output_dir: str | Path | None = None,
    max_items: int | None = None,
) -> tuple[list[dict[str, Any]], Path]:
    """读取正式 release 和原始回答，生成独立的结果评测全套产物。"""
    question_source = Path(questions_path)
    output_source = Path(outputs_path)
    if not question_source.is_file():
        raise FileNotFoundError(f"找不到法律正式题集：{question_source}")
    if not output_source.is_file():
        raise FileNotFoundError(f"找不到法律原始回答：{output_source}")
    questions = read_jsonl(question_source)
    outputs = read_jsonl(output_source)
    if max_items is not None and max_items > 0:
        questions = questions[:max_items]
    judge_client, judge_model = _build_judge_client(questions)
    results, errors = score_outputs(questions, outputs, judge_client, judge_model)

    run_dir = Path(output_dir) if output_dir else timestamped_run_dir(RESULTS_ROOT)
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "legal_evaluation_results.jsonl"
    write_jsonl(result_path, results)
    write_jsonl(run_dir / "legal_evaluation_errors.jsonl", errors)
    (run_dir / "legal_evaluation_report.md").write_text(build_report(results), encoding="utf-8")
    metadata = new_run_metadata(
        "legal_benchmark.result_scoring",
        release_input_path=str(question_source),
        release_sha256=_sha256(question_source),
        model_outputs_path=str(output_source),
        judge_model=judge_model or "",
        question_count=len(questions),
        success_count=sum(1 for row in results if row.get("scoring_status") == "ok"),
        failure_count=len(errors),
        output=str(run_dir),
    )
    metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
    (run_dir / "run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    try:
        export_jsonl(result_path, run_dir / "legal_evaluation_results.xlsx")
    except Exception as exc:
        (run_dir / "excel_error.txt").write_text(str(exc), encoding="utf-8")
    print(f"结果评测目录：{run_dir}")
    return results, run_dir


def main() -> None:
    """解析 04 CLI 参数，启动独立结果评测。"""
    parser = argparse.ArgumentParser(description="法律 Benchmark：04 结果评测")
    parser.add_argument("--questions", "--input", dest="questions", required=True, help="正式题集 release JSONL")
    parser.add_argument("--outputs", required=True, help="03 生成的 legal_model_outputs.jsonl")
    parser.add_argument("--output", required=True, help="评分运行目录")
    parser.add_argument("--max-items", type=int, default=None, help="只评分前 N 题")
    args = parser.parse_args()
    try:
        run(args.questions, args.outputs, args.output, args.max_items)
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()



