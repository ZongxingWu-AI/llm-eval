"""开放题 Pairwise Judge 执行模块。

输入是问题与两位选手回答、一个或多个裁判模型配置，输出双轮位置交换结果、偏见统计和报告。
模块分离裁判调用、有效结果过滤与多数投票，并把位置标签映射回原始选手。
运行时调用裁判模型，只写 Pairwise 自己的 results 目录。"""

import argparse
import sys
from pathlib import Path

from core import llm_client
from core.data_io import read_jsonl

from tracks.pairwise_judge import bias_stats, pairwise, report
from tracks.pairwise_judge.paths import DATA_ROOT


def _build_judges() -> list[tuple]:
    """用途：根据 JUDGE、JUDGE_2、JUDGE_3 创建启用的裁判列表。

    输入：无参数，读取角色环境变量。
    输出：返回 (client, model) 元组列表。
    副作用：读取环境变量并创建客户端；不调用模型。
    异常或失败处理：主裁判缺 key 时退出；可选裁判未显式配置则跳过。"""

    judges: list[tuple] = []
    for prefix in ("JUDGE", "JUDGE_2", "JUDGE_3"):
        if prefix != "JUDGE" and not llm_client.is_role_configured(prefix):
            continue
        base, key, model = llm_client.read_role(prefix, "deepseek-v4-flash")
        judges.append((llm_client.build_client(base, key), model))
    return judges


def evaluate_rows(rows: list[dict], judges: list[tuple]) -> list[dict]:
    """用途：使用一个或多个裁判评估开放题回答并多数汇总。

    输入：rows：含两个回答的题目；judges：裁判列表。
    输出：返回逐题胜者、分数、理由、偏见和错误字段。
    运行前数据形态：每题已有 answer_a/answer_b。
    运行后数据变化：逐裁判收集 verdict，过滤错误后计算 final_winner。
    副作用：会调用裁判模型并打印进度；不写文件。
    异常或失败处理：全部裁判失败时该题记录错误。"""

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
    """用途：读取选手回答，执行双轮位置交换和多裁判投票，并写入独立运行目录。

    输入：input_path 是含 answer_a/answer_b 的 JSONL；output_dir 指定结果目录；max_items 限制试跑题数。
    输出：返回 (逐题汇总结果列表, 实际运行目录 Path)。
    运行前数据形态：运行前每行只有原始选手回答和身份。
    运行后数据变化：运行后每行增加两轮映射、多裁判胜负、最终多数结果、分数与位置偏见字段。
    副作用：读取环境变量并调用模型完成裁判，创建目录并写 JSONL、Markdown、元数据和可选 Excel。
    异常或失败处理：输入不存在时抛出 FileNotFoundError；单个裁判错误保留在逐题结果中，Excel 失败不影响 JSONL。
    最小示例：一题有三个裁判时先分别完成位置交换，再过滤有效结果并投票。"""

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
    """用途：解析 Pairwise 评测 CLI 参数并调用 run。

    输入：命令行 --input、--output-dir、--max-items。
    输出：成功打印运行目录；失败退出 1。
    副作用：可能调用多个裁判模型并写结果。
    异常或失败处理：捕获异常后打印 stderr 并 SystemExit(1)。"""

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
