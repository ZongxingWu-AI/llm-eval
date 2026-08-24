"""法律真实案例评测执行模块。

项目位置：法律 Benchmark 的 evaluation 阶段。
输入：通过验证的 releases/legal_questions.jsonl 和环境变量中的被测/裁判模型配置。
输出：法律线 results 下独立运行目录，包含逐题 JSONL、错误、Markdown 报告、元数据和可选 Excel。
上下游：上游是冻结并验证后的题集，下游是失败分析、模型比较和项目报告。
副作用：调用被测模型，rubric_judge 题还调用裁判模型；只写法律线结果目录。"""

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
    """用途：逐题调用模型取得被测回答，并按每题 scoring_method 生成法律评分。

    输入：questions 是正式题目；contestant_client/model 是被测配置；judge_client/model 供 rubric_judge 使用。
    输出：返回 (成功结果列表, 错误列表)，结果含回答、verdict、评分详情、延迟和 token。
    运行前数据形态：运行前每行是尚无模型回答的正式题。
    运行后数据变化：运行后成功项增加 model_answer 与 scoring_details，失败项保留 question_id、case_id 和错误。
    副作用：每题调用模型生成回答；rubric_judge 还调用裁判模型；本函数不写文件。
    异常或失败处理：单题异常写入 errors 后继续下一题，避免整批中断。
    最小示例：第二题失败不会删除第一题结果，也不会阻止第三题继续。"""
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
    """用途：按指定字段分组统计 PASS、REVIEW、REJECT 等 verdict 数量。

    输入：results 是逐题结果列表；field 通常为 split 或 task_type。
    输出：返回键到 Counter 的字典。
    运行前数据形态：运行前是一组逐题结果。
    运行后数据变化：运行后得到报告表格所需的分组计数。
    副作用：只处理内存，不写文件、不调用模型。
    异常或失败处理：字段为空时归入“未标注”；空结果返回空字典。"""

    grouped: dict[str, Counter] = defaultdict(Counter)
    for row in results:
        grouped[str(row.get(field) or "未分类")][str(row.get("verdict") or "ERROR")] += 1
    return grouped


def build_report(results: list[dict[str, Any]]) -> str:
    """用途：把法律逐题结果汇总成便于阅读的 Markdown 报告。

    输入：results 是 evaluate_questions 的成功结果列表。
    输出：返回包含总数、总体 verdict、按 split 和 task_type 分组统计的 Markdown 字符串。
    运行前数据形态：运行前是结构化 JSON 结果。
    运行后数据变化：运行后变成可写入 legal_report.md 的文本。
    副作用：只处理内存，不写文件、不调用模型。
    异常或失败处理：空结果仍返回合法报告并显示零数量。"""
    total_counts: Counter[str] = Counter()
    for row in results:
        verdict = row.get("verdict", "ERROR")
        total_counts[verdict] += 1
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
    """用途：根据题目评分方式创建被测模型客户端，并在需要时创建裁判客户端。

    输入：questions 是正式题目列表，用于判断是否存在 rubric_judge。
    输出：返回 contestant_client、contestant_model、judge_client、judge_model 四元组。
    运行前数据形态：运行前只有题集和环境配置。
    运行后数据变化：运行后得到 evaluate_questions 可直接使用的客户端与模型名。
    副作用：读取 .env 和角色环境变量并创建客户端；不发起实际模型请求、不写文件。
    异常或失败处理：必需角色配置缺失时由 core.llm_client 抛出明确错误；无需裁判时后两项为空。"""

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
    """用途：执行一次完整法律 Benchmark，并把所有产物隔离写入法律线运行目录。

    输入：input_path 是正式题集；output_dir 可指定运行目录；max_items 用于小规模试跑。
    输出：返回 (逐题成功结果, 实际运行目录 Path)。
    运行前数据形态：运行前是一行一道冻结题目。
    运行后数据变化：运行后每次评测拥有独立结果目录，不污染 C-Eval 或 Pairwise Judge。
    副作用：调用被测模型和可能的裁判模型；创建目录并写 legal_results.jsonl、errors.jsonl、legal_report.md、run_metadata.json 和可选 xlsx。
    异常或失败处理：题集不存在时抛出 FileNotFoundError；Excel 导出失败只写 excel_error.txt，不影响 JSON 结果。"""
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
    """用途：提供法律评测 CLI，把题集路径、输出目录和最大题数传给 run。

    输入：参数来自 argparse，默认读取 releases/legal_questions.jsonl 并创建时间戳结果目录。
    输出：成功时打印结果目录；失败打印错误并以状态码 1 退出。
    运行前数据形态：运行前是冻结题集与命令行参数。
    运行后数据变化：运行后生成完整逐题结果、错误、报告和元数据。
    副作用：会调用被测模型及必要裁判模型，并写入法律线 results。
    异常或失败处理：参数错误由 argparse 处理；run 异常转换为非零退出。"""

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
