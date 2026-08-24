"""项目模块：tracks/pairwise_judge/report.py。

本文件属于三条评测线或公共工具层的一部分，负责完成本文件名对应的处理步骤。输入来自上游函数或数据目录，输出返回给下游函数或写入对应结果目录。

项目位置：tracks/pairwise_judge/report.py。
主要用途：开放题 LLM-as-Judge 评测线，负责生成回答、位置交换裁判、多裁判统计和报告。
输入：输入来自本评测线的 data 目录、裁判 Prompt 和公共模型客户端。
输出：输出写入本评测线的 results 目录，供偏见分析和报告阅读。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：生成和裁判模块会调用模型；统计和报告模块只处理内存数据或写结果文件。
"""

import json
from pathlib import Path

from core.data_io import write_jsonl
from core.run_metadata import timestamped_run_dir

from tracks.pairwise_judge.paths import RESULTS_ROOT


def _build_report(results: list[dict], judge_models: list[str], stats: dict) -> str:
    """为同一文件中的公开流程提供一个小而明确的辅助步骤。

参数：results、judge_models、stats。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    lines = ["# 裁判成对比较报告", "", f"- 选手 A：{stats['model_a']}", f"- 选手 B：{stats['model_b']}"]
    lines.extend(f"- 裁判{index + 1}：{model}" for index, model in enumerate(judge_models))
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
    """完成当前模块中的一个处理步骤。

参数：results、judges、stats、output_dir。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    run_dir = Path(output_dir) if output_dir else timestamped_run_dir(RESULTS_ROOT)
    run_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = run_dir / "judge_pairs.jsonl"
    write_jsonl(jsonl_path, results)
    judge_models = [model for _, model in judges]
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
