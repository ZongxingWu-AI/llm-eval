"""法律真实案例的模型作答入口。

本阶段只读取冻结 release 并调用被测模型，保存可复用的原始回答；不加载裁判客户端，
也不执行任何规则、红线或 Rubric Judge 评分。评分由后续 04 结果评测阶段独立完成。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import llm_client
from core.data_io import read_jsonl, write_jsonl
from core.project_paths import LEGAL_RESULTS_ROOT as RESULTS_ROOT
from core.run_metadata import new_run_metadata, timestamped_run_dir


def _validate_question_ids(questions: list[dict[str, Any]]) -> None:
    """校验 release 中的 question_id 非空且唯一，避免原始回答无法关联题目。"""
    seen: set[str] = set()
    for question in questions:
        question_id = str(question.get("question_id") or "").strip()
        if not question_id:
            raise ValueError("正式题集中存在缺失 question_id")
        if question_id in seen:
            raise ValueError(f"正式题集中存在重复 question_id：{question_id}")
        seen.add(question_id)


def _sha256(path: Path) -> str:
    """计算 release 文件的 SHA-256，写入运行元数据以便复现。"""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_CONTEXT_LABELS = {
    "self_contained": "【必要背景】",
    "source_excerpt": "【原文材料】",
    "full_document": "【完整案件材料】",
    "scenario": "【风险场景】",
}


def _text_value(value: Any) -> str:
    """把题集中的上下文值转换为被测模型可以直接读取的文本。"""
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, indent=2)


def _build_model_input(question: dict[str, Any]) -> str:
    """依据 context_type 组装被测模型输入；旧题没有 context 时原样回退。"""
    question_text = _text_value(question.get("question"))
    context = _text_value(question.get("context"))
    if not context:
        return question_text

    context_type = str(question.get("context_type") or "").strip()
    label = _CONTEXT_LABELS.get(context_type, "【案件材料】")
    return f"{label}\n{context}\n\n【问题】\n{question_text}"


def generate_answers(
    questions: list[dict[str, Any]],
    contestant_client: Any,
    contestant_model: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """逐题调用被测模型并返回原始回答记录与调用错误。

    输入：正式 release 题目、被测模型客户端和模型名。
    输出：成功列表只含题目元数据、model_answer 和调用元数据；错误列表记录失败题目。
    重要边界：即使题目的 scoring_method 是 rubric_judge，本函数也绝不创建或调用裁判。
    """
    _validate_question_ids(questions)
    outputs: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, question in enumerate(questions, start=1):
        question_id = str(question["question_id"])
        print(f"[法律模型作答] {index}/{len(questions)} {question_id} ...", end=" ", flush=True)
        try:
            answer, latency, tokens, finish_reason = llm_client.call_model(
                contestant_client,
                contestant_model,
                _build_model_input(question),
                0,
                8192,
            )
            output = {
                "question_id": question_id,
                "case_id": question.get("case_id", ""),
                "split": question.get("split", ""),
                "primary_issue": question.get("primary_issue", ""),
                "dimension_id": question.get("dimension_id", ""),
                "task_type": question.get("task_type", ""),
                "context_type": question.get("context_type", ""),
                "difficulty": question.get("difficulty", ""),
                "question": question.get("question", ""),
                "model_answer": answer,
                "latency_seconds": latency,
                "total_tokens": tokens,
                "finish_reason": finish_reason,
            }
            outputs.append(output)
            print("OK")
        except Exception as exc:
            errors.append({
                "question_id": question_id,
                "case_id": question.get("case_id", ""),
                "dimension_id": question.get("dimension_id", ""),
                "task_type": question.get("task_type", ""),
                "context_type": question.get("context_type", ""),
                "error": str(exc),
            })
            print(f"ERROR: {exc}")
    return outputs, errors


def _build_contestant_client() -> tuple[Any, str]:
    """从 CONTESTANT_A 配置创建被测模型客户端，不读取 JUDGE 配置。"""
    llm_client.load_env()
    base, key, model = llm_client.read_role("CONTESTANT_A", "deepseek-v4-flash")
    return llm_client.build_client(base, key), model


def run(
    input_path: str | Path,
    output_dir: str | Path | None = None,
    max_items: int | None = None,
) -> tuple[list[dict[str, Any]], Path]:
    """执行一次 03 模型作答并保存可供 04 重复评分的原始产物。

    输入：input_path 是正式 release；output_dir 是回答运行目录；max_items 用于 smoke 试跑。
    输出：返回 (成功原始回答列表, 实际运行目录)。目录包含 outputs、errors 和 run_metadata。
    副作用：只调用被测模型并写文件，不创建裁判客户端，不产生 verdict 或 scoring_details。
    """
    source = Path(input_path)
    if not source.is_file():
        raise FileNotFoundError(f"找不到法律正式题集：{source}")
    questions = read_jsonl(source)
    if max_items is not None and max_items > 0:
        questions = questions[:max_items]
    _validate_question_ids(questions)

    contestant_client, contestant_model = _build_contestant_client()
    outputs, errors = generate_answers(questions, contestant_client, contestant_model)
    run_dir = Path(output_dir) if output_dir else timestamped_run_dir(RESULTS_ROOT)
    run_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(run_dir / "legal_model_outputs.jsonl", outputs)
    write_jsonl(run_dir / "legal_model_errors.jsonl", errors)

    metadata = new_run_metadata(
        "legal_benchmark.model_answering",
        release_input_path=str(source),
        release_sha256=_sha256(source),
        contestant_model=contestant_model,
        question_count=len(questions),
        success_count=len(outputs),
        failure_count=len(errors),
        output=str(run_dir),
    )
    metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
    (run_dir / "run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(f"原始回答目录：{run_dir}")
    return outputs, run_dir


def main() -> None:
    """解析 03 CLI 参数，读取正式 release 并启动模型作答。"""
    parser = argparse.ArgumentParser(description="法律 Benchmark：03 模型作答")
    parser.add_argument("--input", required=True, help="正式题集 release JSONL")
    parser.add_argument("--output", help="原始回答运行目录；默认写入法律 results/时间戳目录")
    parser.add_argument("--max-items", "--max-questions", type=int, default=None, help="只作答前 N 题")
    args = parser.parse_args()
    try:
        run(args.input, args.output, args.max_items)
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

