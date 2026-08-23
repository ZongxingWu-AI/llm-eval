#!/usr/bin/env python3
"""把一次评测的结果写成文件：jsonl、xlsx、md 报告，放在时间戳目录里。"""

import json  # 用来写 jsonl
import os    # 用来拼路径、建目录
import time  # 用来生成时间戳

import pandas as pd  # 用来写 Excel


# 项目根目录：本文件在 llm-eval/report/ 下，往上一级就是 llm-eval。
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")


def write_run(results, judges, stats):
    """把一次运行的结果写进一个时间戳目录。

    输入：
      results 是每题的结果字典列表；
      judges  是裁判列表，每项是 (客户端, 模型名)；
      stats   是 bias_stats.compute_stats 返回的统计字典。
    输出：结果目录的路径（字符串）。
    """
    # 运行前：还没有目录。
    # 运行后：stamp 变成时间戳字符串，例如 "20260823_153000"。
    stamp = time.strftime("%Y%m%d_%H%M%S")
    # 运行后：run_dir 变成本次运行的结果目录路径。
    run_dir = os.path.join(RESULTS_DIR, stamp)
    os.makedirs(run_dir, exist_ok=True)

    # 1) 写 jsonl：每行是一题的结果。
    jsonl_path = os.path.join(run_dir, "judge_pairs.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as file_handle:
        for result in results:
            line = json.dumps(result, ensure_ascii=False)
            file_handle.write(line + "\n")

    # 2) 写 xlsx：一张表，每行是一题，每列是一个字段。
    xlsx_path = os.path.join(run_dir, "judge_pairs.xlsx")
    dataframe = pd.DataFrame(results)
    dataframe.to_excel(xlsx_path, sheet_name="judge_pairs", index=False)

    # 3) 写 md 报告。
    md_path = os.path.join(run_dir, "judge_report.md")
    # 从 judges 里取出模型名列表，方便写报告。
    judge_models = []
    for client_j, model_j in judges:
        judge_models.append(model_j)
    markdown = _build_report(results, judge_models, stats, jsonl_path, xlsx_path)
    with open(md_path, "w", encoding="utf-8") as file_handle:
        file_handle.write(markdown)

    return run_dir


def _build_report(results, judge_models, stats, jsonl_path, xlsx_path):
    """生成 Markdown 报告文本。"""
    lines = []
    lines.append("# 裁判成对比较报告")
    lines.append("")
    lines.append("- 运行时间：" + time.strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("- 选手 A：" + stats["model_a"])
    lines.append("- 选手 B：" + stats["model_b"])
    for j in range(len(judge_models)):
        lines.append("- 裁判" + str(j + 1) + "：" + judge_models[j])
    lines.append("")
    lines.append("## 每题结果")
    lines.append("")
    lines.append("| 题号 | 最终胜者 | A长度 | B长度 | A总分 | B总分 | judge1 | judge2 | judge3 | 位置偏见 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for result in results:
        cells = [
            str(result.get("id", "")),
            str(result.get("final_winner", "")),
            str(result.get("answer_a_len", "")),
            str(result.get("answer_b_len", "")),
            str(result.get("score_a_total", "")),
            str(result.get("score_b_total", "")),
            str(result.get("judge1_winner", "")),
            str(result.get("judge2_winner", "")),
            str(result.get("judge3_winner", "")),
            str(result.get("judge1_position_bias", "")),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## 摘要统计")
    lines.append("")
    lines.append("- 题量：" + str(stats["total"]) + "，错误：" + str(stats["errors"]))
    lines.append("- 主裁判位置偏见题数：" + str(stats["bias_count"]))
    lines.append("- 最终胜者（多数投票）：A " + str(stats["win_a"]) + " / B " + str(stats["win_b"]) + " / 平 " + str(stats["ties"]))
    # 更长回答胜率。
    if stats["longer_decided"] > 0:
        rate = stats["longer_wins"] / stats["longer_decided"] * 100
        lines.append("- 更长回答胜率：" + str(stats["longer_wins"]) + "/" + str(stats["longer_decided"]) + " (" + format(rate, ".1f") + "%)")
    else:
        lines.append("- 更长回答胜率：无有胜负且长度不同的题")
    # 每个裁判的胜场与同族胜率。
    for j in range(len(judge_models)):
        model_j = judge_models[j]
        family_j = model_j.split("-")[0]
        decided = stats["judge_win_a"][j] + stats["judge_win_b"][j]
        if stats["judge_side"][j] == "":
            lines.append("- 裁判" + str(j + 1) + " " + model_j + "（族=" + family_j + "，与两选手不同族）：A " + str(stats["judge_win_a"][j]) + " / B " + str(stats["judge_win_b"][j]) + " / 平 " + str(stats["judge_win_tie"][j]))
        else:
            if stats["judge_same_decided"][j] > 0:
                same_rate = stats["judge_same_wins"][j] / stats["judge_same_decided"][j] * 100
                lines.append("- 裁判" + str(j + 1) + " " + model_j + "（族=" + family_j + "，与选手" + stats["judge_side"][j] + "同族）：A " + str(stats["judge_win_a"][j]) + " / B " + str(stats["judge_win_b"][j]) + " / 平 " + str(stats["judge_win_tie"][j]) + "，同族胜率 " + format(same_rate, ".1f") + "%")
            else:
                lines.append("- 裁判" + str(j + 1) + " " + model_j + "（族=" + family_j + "，与选手" + stats["judge_side"][j] + "同族）：A " + str(stats["judge_win_a"][j]) + " / B " + str(stats["judge_win_b"][j]) + " / 平 " + str(stats["judge_win_tie"][j]))
    lines.append("")
    lines.append("## 文件")
    lines.append("")
    lines.append("- JSONL：" + jsonl_path)
    lines.append("- Excel：" + xlsx_path)
    return "\n".join(lines)
