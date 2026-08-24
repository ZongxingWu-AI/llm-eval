"""Pairwise 运行产物与报告模块。

输入是逐题裁判结果、错误、裁判配置和运行信息，输出 JSONL、Markdown、元数据及可选 Excel。
该模块由 evaluate 在评测末尾调用，只写 Pairwise 自己的运行目录，不调用模型。"""

import json
from pathlib import Path

from core.data_io import write_jsonl
from core.run_metadata import timestamped_run_dir

from tracks.pairwise_judge.paths import RESULTS_ROOT


def _build_report(results: list[dict], judge_models: list[str], stats: dict) -> str:
    """用途：把逐题结果和偏见统计组装为 Markdown。

    输入：results、judge_models、stats。
    输出：返回完整 Markdown 字符串。
    副作用：只处理内存，不调用模型、不写文件。
    异常或失败处理：stats 缺必需键时向上抛出 KeyError。"""

    lines = ["# 裁判成对比较报告", "", f"- 选手 A：{stats['model_a']}", f"- 选手 B：{stats['model_b']}"]
    for index, model in enumerate(judge_models):
        judge_line = f"- 裁判{index + 1}：{model}"
        lines.append(judge_line)
    lines.extend(["", "## 每题结果", "", "| 题号 | 最终胜者 | A长度 | B长度 | A总分 | B总分 | judge1 | judge2 | judge3 | 位置偏见 |",
                  "|---|---|---|---|---|---|---|---|---|---|"])
    for result in results:
        cells = [result.get("id", ""), result.get("final_winner", ""), result.get("answer_a_len", ""),
                 result.get("answer_b_len", ""), result.get("score_a_total", ""), result.get("score_b_total", ""),
                 result.get("judge1_winner", ""), result.get("judge2_winner", ""), result.get("judge3_winner", ""),
                 result.get("judge1_position_bias", "")]
        lines.append("| " + " | ".join(map(str, cells)) + " |")
    lines.extend(["", "## 摘要统计", "", f"- 题量：{stats['total']}，错误：{stats['errors']}",
                  f"- 主裁判位置偏见题数：{stats['bias_count']}",
                  f"- 最终胜者：A {stats['win_a']} / B {stats['win_b']} / 平 {stats['ties']}"])
    if stats["longer_decided"]:
        rate = stats["longer_wins"] / stats["longer_decided"] * 100
        lines.append(f"- 更长回答胜率：{stats['longer_wins']}/{stats['longer_decided']} ({rate:.1f}%)")
    for index, model in enumerate(judge_models):
        lines.append(f"- 裁判{index + 1} {model}：A {stats['judge_win_a'][index]} / B {stats['judge_win_b'][index]} / 平 {stats['judge_win_tie'][index]}")
    return "\n".join(lines) + "\n"


def write_run(results: list[dict], judges: list[tuple], stats: dict, output_dir: str | Path | None = None) -> Path:
    """用途：把一次 Pairwise 运行保存到独立目录。

    输入：results、judges、stats、可选 output_dir。
    输出：返回实际运行目录。
    副作用：创建目录并写 JSONL、Markdown、元数据和可选 Excel。
    异常或失败处理：Excel 导出失败时写 excel_error.txt，不影响其他结果。"""

    run_dir = Path(output_dir) if output_dir else timestamped_run_dir(RESULTS_ROOT)
    run_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = run_dir / "judge_pairs.jsonl"
    write_jsonl(jsonl_path, results)
    judge_models: list[str] = []
    for judge in judges:
        model = judge[1]
        judge_models.append(model)
    (run_dir / "judge_report.md").write_text(_build_report(results, judge_models, stats), encoding="utf-8")
    (run_dir / "run_metadata.json").write_text(
        json.dumps({"track": "pairwise_judge", "judge_models": judge_models, "stats": stats}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        from tools.export_excel import export_jsonl
        export_jsonl(jsonl_path, run_dir / "judge_pairs.xlsx")
    except Exception as exc:
        (run_dir / "excel_error.txt").write_text(str(exc), encoding="utf-8")
    return run_dir
