"""项目模块：tracks/legal_benchmark/evaluation/run.py。

本文件属于三条评测线或公共工具层的一部分，负责完成本文件名对应的处理步骤。输入来自上游函数或数据目录，输出返回给下游函数或写入对应结果目录。

项目位置：tracks/legal_benchmark/evaluation/run.py。
主要用途：法律真实案例 Benchmark，负责判决书解析、结构化提取、出题、校验和法律评测。
输入：输入来自法律线 data/raw、parsed、cleaned、drafts、releases 或 taxonomy/schema。
输出：输出按生命周期写入法律线对应 data 子目录或 results 目录。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：ingestion/extraction/generation/evaluation 可能写文件；只有带模型选项时才调用模型。
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

from pathlib import Path
from typing import Any

from core import llm_client
from core.data_io import read_jsonl, write_jsonl
from core.run_metadata import new_run_metadata, timestamped_run_dir
from tracks.legal_benchmark.paths import DATA_ROOT, RESULTS_ROOT
from tracks.legal_benchmark.scoring import legal_scorer


def evaluate_questions(
    questions: list[dict[str, Any]],
    contestant_client: Any,
    contestant_model: str,
    judge_client: Any = None,
    judge_model: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """逐题调用被测模型并完成法律题评分。

    调用前输入是正式题集和已经配置好的被测模型客户端；调用后每道成功题会
    形成一条结果，包含模型回答、评分 verdict、评分详情、延迟、token 数和结束原因。
    单题异常进入 ``errors`` 列表，不会中断其他题目。函数会调用模型，但不在这里写文件，
    由 ``run`` 负责把结果写入法律线自己的 results 目录。
    """
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, question in enumerate(questions, start=1):
        question_id = question.get("question_id", "")
        print(f"[法律评测] {index}/{len(questions)} {question_id} ...", end=" ", flush=True)
        try:
            answer, latency, tokens, finish_reason = llm_client.call_model(
                contestant_client, contestant_model, question.get("question", ""), 0, 8192,
            )
            scoring = legal_scorer.score_one(question, answer, judge_client, judge_model)
            row = {
                "question_id": question_id,
                "case_id": question.get("case_id", ""),
                "split": question.get("split", ""),
                "primary_issue": question.get("primary_issue", ""),
                "task_type": question.get("task_type", ""),
                "difficulty": question.get("difficulty", ""),
                "question": question.get("question", ""),
                "model_answer": answer,
                "reference_answer": question.get("reference_answer", ""),
                "scoring_method": question.get("scoring_method", ""),
                "verdict": scoring.get("verdict", ""),
                "reason": scoring.get("reason", ""),
                "latency_seconds": latency,
                "total_tokens": tokens,
                "finish_reason": finish_reason,
                "scoring_details": scoring,
            }
            results.append(row)
            print(row["verdict"])
        except Exception as exc:
            error = {"question_id": question_id, "case_id": question.get("case_id", ""), "error": str(exc)}
            errors.append(error)
            print(f"ERROR: {exc}")
    return results, errors


def _counts_by(results: list[dict[str, Any]], field: str) -> dict[str, Counter]:
    """为同一文件中的公开流程提供一个小而明确的辅助步骤。

参数：results、field。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    grouped: dict[str, Counter] = defaultdict(Counter)
    for row in results:
        grouped[str(row.get(field) or "未分类")][str(row.get("verdict") or "ERROR")] += 1
    return grouped


def build_report(results: list[dict[str, Any]]) -> str:
    """把法律评测逐题结果汇总为 Markdown 报告。输入是带 split、任务类型和 verdict 的结果列表，输出是按总数和分组统计组织的报告文本。"""
    total_counts = Counter(row.get("verdict", "ERROR") for row in results)
    lines = [
        "# 法律真实案例 Benchmark 评测报告", "",
        f"- 题量：{len(results)}",
        f"- PASS：{total_counts['PASS']} / REVIEW：{total_counts['REVIEW']} / REJECT：{total_counts['REJECT']}",
        "", "## 每题结果", "",
        "| 题号 | split | 任务类型 | 评分方式 | 结论 |",
        "|---|---|---|---|---|",
    ]
    for row in results:
        cells = [
            row.get("question_id", ""),
            row.get("split", ""),
            row.get("task_type", ""),
            row.get("scoring_method", ""),
            row.get("verdict", ""),
        ]
        escaped_cells: list[str] = []
        for value in cells:
            escaped_cells.append(str(value).replace("|", "\\|"))
        lines.append("| " + " | ".join(escaped_cells) + " |")
    for title, field in (("按 split 统计", "split"), ("按任务类型统计", "task_type")):
        lines.extend(["", f"## {title}", ""])
        for label, counts in sorted(_counts_by(results, field).items()):
            lines.append(f"- {label}：PASS {counts['PASS']} / REVIEW {counts['REVIEW']} / REJECT {counts['REJECT']}")
    return "\n".join(lines) + "\n"


def _build_clients(questions: list[dict[str, Any]]) -> tuple[Any, str, Any, str | None]:
    """根据题集中的评分方式创建被测模型和可选裁判客户端。

    只要题集中出现一题 ``rubric_judge``，就读取 ``JUDGE`` 配置；否则不创建
    裁判客户端。返回值依次是被测客户端、被测模型名、裁判客户端和裁判模型名。
    这个函数会读取环境变量并创建 API 客户端，但不发起实际模型请求。
    """

    llm_client.load_env()
    base, key, contestant_model = llm_client.read_role("CONTESTANT_A", "deepseek-v4-flash")
    contestant_client = llm_client.build_client(base, key)

    needs_judge = False
    for row in questions:
        if row.get("scoring_method") == "rubric_judge":
            needs_judge = True
            break

    judge_client: Any = None
    judge_model: str | None = None
    if needs_judge:
        judge_base, judge_key, judge_model = llm_client.read_role("JUDGE", "deepseek-v4-flash")
        judge_client = llm_client.build_client(judge_base, judge_key)
    return contestant_client, contestant_model, judge_client, judge_model


def run(
    input_path: str | Path = DATA_ROOT / "releases" / "legal_questions.jsonl",
    output_dir: str | Path | None = None,
    max_items: int | None = None,
) -> tuple[list[dict[str, Any]], Path]:
    """运行一次完整的法律 Benchmark，并隔离写入法律线结果目录。

    输入是正式题集路径、可选输出目录和试跑数量；输出返回“逐题结果列表 + 本次
    运行目录”。运行目录包含 ``legal_results.jsonl``、``errors.jsonl``、Markdown 报告、
    ``run_metadata.json``，以及可用时的 Excel。函数会调用模型、写文件和记录运行元数据，
    但不会修改 C-Eval 或 Pairwise Judge 的结果目录。
    """
    source = Path(input_path)
    if not source.is_file():
        raise FileNotFoundError(f"找不到法律题集：{source}")
    questions = read_jsonl(source)
    if max_items is not None and max_items > 0:
        questions = questions[:max_items]
    contestant_client, contestant_model, judge_client, judge_model = _build_clients(questions)
    results, errors = evaluate_questions(
        questions, contestant_client, contestant_model, judge_client, judge_model,
    )
    run_dir = Path(output_dir) if output_dir else timestamped_run_dir(RESULTS_ROOT)
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "legal_results.jsonl"
    write_jsonl(result_path, results)
    write_jsonl(run_dir / "errors.jsonl", errors)
    (run_dir / "legal_report.md").write_text(build_report(results), encoding="utf-8")
    metadata = new_run_metadata(
        "legal_benchmark.evaluation", input=str(source), output=str(run_dir),
        question_count=len(questions), result_count=len(results), error_count=len(errors),
        contestant_model=contestant_model, judge_model=judge_model or "",
    )
    metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
    (run_dir / "run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    try:
        from tools.export_excel import export_jsonl
        export_jsonl(result_path, run_dir / "legal_results.xlsx")
    except Exception as exc:
        (run_dir / "excel_error.txt").write_text(str(exc), encoding="utf-8")
    print(f"结果目录：{run_dir}")
    return results, run_dir


def main() -> None:
    """完成当前模块中的一个处理步骤。

参数：无。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    parser = argparse.ArgumentParser(description="运行法律真实案例 Benchmark 评测")
    parser.add_argument("--input", default=str(DATA_ROOT / "releases" / "legal_questions.jsonl"), help="正式题集 JSONL")
    parser.add_argument("--output", help="本次运行输出目录；默认写入法律线 results/时间戳目录")
    parser.add_argument("--max-items", "--max-questions", type=int, default=None, help="只评测前 N 题")
    args = parser.parse_args()
    try:
        run(args.input, args.output, args.max_items)
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
