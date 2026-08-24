"""项目模块：tracks/pairwise_judge/evaluate.py。

本文件属于三条评测线或公共工具层的一部分，负责完成本文件名对应的处理步骤。输入来自上游函数或数据目录，输出返回给下游函数或写入对应结果目录。

项目位置：tracks/pairwise_judge/evaluate.py。
主要用途：开放题 LLM-as-Judge 评测线，负责生成回答、位置交换裁判、多裁判统计和报告。
输入：输入来自本评测线的 data 目录、裁判 Prompt 和公共模型客户端。
输出：输出写入本评测线的 results 目录，供偏见分析和报告阅读。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：生成和裁判模块会调用模型；统计和报告模块只处理内存数据或写结果文件。
"""

import argparse
import sys
from pathlib import Path

from core import llm_client
from core.data_io import read_jsonl

from tracks.pairwise_judge import bias_stats, pairwise, report
from tracks.pairwise_judge.paths import DATA_ROOT


def _build_judges() -> list[tuple]:
    """为同一文件中的公开流程提供一个小而明确的辅助步骤。

参数：无。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    judges: list[tuple] = []
    for prefix in ("JUDGE", "JUDGE_2", "JUDGE_3"):
        if prefix != "JUDGE" and not llm_client.is_role_configured(prefix):
            continue
        base, key, model = llm_client.read_role(prefix, "deepseek-v4-flash")
        judges.append((llm_client.build_client(base, key), model))
    return judges


def evaluate_rows(rows: list[dict], judges: list[tuple]) -> list[dict]:
    """逐题调用模型并计算 C-Eval 结果。调用前是题目列表和客户端，调用后每道题增加预测答案、正确答案、是否正确、耗时和错误信息。"""

    results: list[dict] = []
    for index, row in enumerate(rows, start=1):
        print(f"[裁判] {index}/{len(rows)} {row.get('id', '')} ...", end=" ", flush=True)
        verdicts = []
        for client, model in judges:
            verdict = pairwise.judge_one(row, client, model)
            verdicts.append(verdict)

        valid = []
        for verdict in verdicts:
            if not verdict["error"]:
                valid.append(verdict["judge_winner"])

        primary = verdicts[0] if verdicts else {}
        result = {
            "id": row.get("id", ""), "question": row.get("question", ""),
            "answer_a_len": len(row.get("answer_a", "")), "answer_b_len": len(row.get("answer_b", "")),
            "judge1_winner": verdicts[0]["judge_winner"] if len(verdicts) > 0 else "",
            "judge1_position_bias": verdicts[0]["position_bias"] if len(verdicts) > 0 else False,
            "judge2_winner": verdicts[1]["judge_winner"] if len(verdicts) > 1 else "",
            "judge2_position_bias": verdicts[1]["position_bias"] if len(verdicts) > 1 else False,
            "judge3_winner": verdicts[2]["judge_winner"] if len(verdicts) > 2 else "",
            "judge3_position_bias": verdicts[2]["position_bias"] if len(verdicts) > 2 else False,
            "round1_winner": primary.get("round1_winner", ""), "round2_winner": primary.get("round2_winner", ""),
            "score_a_total": primary.get("score_a_total", 0), "score_b_total": primary.get("score_b_total", 0),
            "final_winner": pairwise.majority_winner(valid) if valid else "",
            "reason_1": primary.get("reason_1", ""), "reason_2": primary.get("reason_2", ""),
            "error": "" if valid else "全部裁判输出无法解析",
        }
        results.append(result)
        print(f"winner={result['final_winner']}" if not result["error"] else f"ERROR: {result['error']}")
    return results


def run(input_path: str | Path | None = None, output_dir: str | Path | None = None,
        max_items: int | None = None) -> tuple[list[dict], Path]:
    """完成当前模块中的一个处理步骤。

参数：input_path、output_dir、max_items。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    source = Path(input_path) if input_path else DATA_ROOT / "judge_answers.jsonl"
    if not source.is_file():
        raise FileNotFoundError(f"找不到回答文件：{source}；请先运行 python -m tracks.pairwise_judge.generate_answers")
    rows = read_jsonl(source)
    if max_items is not None and max_items > 0:
        rows = rows[:max_items]
    llm_client.load_env()
    judges = _build_judges()
    results = evaluate_rows(rows, judges)
    stats = bias_stats.compute_stats(results, rows, judges)
    run_dir = report.write_run(results, judges, stats, output_dir)
    print(f"结果目录：{run_dir}")
    return results, run_dir


def main() -> None:
    """完成当前模块中的一个处理步骤。

参数：无。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    parser = argparse.ArgumentParser(description="运行带位置交换、多裁判和偏见统计的成对比较")
    parser.add_argument("--input", help="选手回答 JSONL")
    parser.add_argument("--output", help="本次运行输出目录")
    parser.add_argument("--max-items", "--max-questions", type=int, default=None, help="只跑前 N 题")
    args = parser.parse_args()
    try:
        run(args.input, args.output, args.max_items)
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
