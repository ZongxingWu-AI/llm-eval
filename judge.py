#!/usr/bin/env python3
"""M3 裁判评测入口：组装各模块，跑完成对比较并落盘报告。

运行:
    python judge.py
    python judge.py --max-questions 2
"""

import argparse  # 解析命令行参数
import json      # 解析回答文件里的 JSON 行
import os        # 拼路径
import sys       # 打印错误、退出

from runner import llm_client      # 读配置、调模型
from judge import pairwise         # 成对比较核心逻辑
from metrics import bias_stats     # 三大偏见统计
from report import writer          # 写结果文件与报告


# 脚本所在目录，用来拼 data 路径。
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")


def load_answers():
    """读取 generate_answers.py 生成的两版回答。

    输入：无。
    输出：回答字典列表，每条含 question / answer_a / answer_b / model_a / model_b。
    """
    # 运行前：还没有读文件。
    # 运行后：path 变成回答文件的路径。
    path = os.path.join(DATA_DIR, "judge_answers.jsonl")
    if not os.path.exists(path):
        print("[错误] 找不到回答文件：" + path, file=sys.stderr)
        print("请先运行：python generate_answers.py", file=sys.stderr)
        sys.exit(1)

    rows = []
    with open(path, encoding="utf-8") as file_handle:
        for line in file_handle:
            line = line.strip()
            if line == "":
                continue
            # 运行前：line 是一行 JSON 文本。
            # 运行后：把这一行解析成字典，加进列表。
            row = json.loads(line)
            rows.append(row)
    return rows


def run(max_questions):
    """主流程：构建裁判、逐题判定、统计、落盘、打印简报。"""
    llm_client.load_env()

    # 构建裁判列表：主裁判必用，第 2、3 个裁判配置了才用。
    # 运行后：judges 是一个列表，每项是 (客户端, 模型名)。
    judges = []
    base, key, model = llm_client.read_role("JUDGE", "deepseek-v4-flash")
    judges.append((llm_client.build_client(base, key), model))
    if llm_client.is_role_configured("JUDGE_2"):
        base2, key2, model2 = llm_client.read_role("JUDGE_2", "deepseek-v4-flash")
        judges.append((llm_client.build_client(base2, key2), model2))
    if llm_client.is_role_configured("JUDGE_3"):
        base3, key3, model3 = llm_client.read_role("JUDGE_3", "deepseek-v4-flash")
        judges.append((llm_client.build_client(base3, key3), model3))

    rows = load_answers()
    # 运行前：rows 是全部回答。
    # 运行后：rows 变成前 N 条（传了 --max-questions 时）。
    if max_questions is not None and max_questions > 0:
        rows = rows[:max_questions]

    results = []
    total = len(rows)
    for i, row in enumerate(rows, start=1):
        print("[裁判] " + str(i) + "/" + str(total) + " " + row["id"] + " ...", end=" ", flush=True)
        # 逐个裁判做两轮判定。
        verdicts = []
        for client_j, model_j in judges:
            verdict = pairwise.judge_one(row, client_j, model_j)
            verdicts.append(verdict)

        # 收集有效判定（没有 error 的），用于多数投票。
        valid_winners = []
        for verdict in verdicts:
            if verdict["error"] == "":
                valid_winners.append(verdict["judge_winner"])

        # 结果行固定放 3 个裁判的位置，没启用的字段留空。
        judge1_winner = ""
        judge2_winner = ""
        judge3_winner = ""
        judge1_bias = False
        judge2_bias = False
        judge3_bias = False
        round1_winner = ""
        round2_winner = ""
        score_a_total = 0
        score_b_total = 0
        reason_1 = ""
        reason_2 = ""
        row_error = ""
        if len(verdicts) > 0:
            judge1_winner = verdicts[0]["judge_winner"]
            judge1_bias = verdicts[0]["position_bias"]
            round1_winner = verdicts[0]["round1_winner"]
            round2_winner = verdicts[0]["round2_winner"]
            score_a_total = verdicts[0]["score_a_total"]
            score_b_total = verdicts[0]["score_b_total"]
            reason_1 = verdicts[0]["reason_1"]
            reason_2 = verdicts[0]["reason_2"]
        if len(verdicts) > 1:
            judge2_winner = verdicts[1]["judge_winner"]
            judge2_bias = verdicts[1]["position_bias"]
        if len(verdicts) > 2:
            judge3_winner = verdicts[2]["judge_winner"]
            judge3_bias = verdicts[2]["position_bias"]

        # 多数投票决定最终胜者；没有有效判定就记 error。
        if len(valid_winners) == 0:
            final_winner = ""
            row_error = "全部裁判输出无法解析"
        else:
            final_winner = pairwise.majority_winner(valid_winners)

        # 运行后：result 变成这道题的完整结果字典。
        result = {
            "id": row["id"],
            "question": row["question"],
            "answer_a_len": len(row["answer_a"]),
            "answer_b_len": len(row["answer_b"]),
            "judge1_winner": judge1_winner,
            "judge1_position_bias": judge1_bias,
            "judge2_winner": judge2_winner,
            "judge2_position_bias": judge2_bias,
            "judge3_winner": judge3_winner,
            "judge3_position_bias": judge3_bias,
            "round1_winner": round1_winner,
            "round2_winner": round2_winner,
            "score_a_total": score_a_total,
            "score_b_total": score_b_total,
            "final_winner": final_winner,
            "reason_1": reason_1,
            "reason_2": reason_2,
            "error": row_error,
        }
        results.append(result)
        if result["error"] == "":
            print("winner=" + result["final_winner"])
        else:
            print("ERROR: " + result["error"])

    # 统计三大偏见，再落盘到时间戳目录。
    stats = bias_stats.compute_stats(results, rows, judges)
    run_dir = writer.write_run(results, judges, stats)

    # 控制台只打印简报，完整内容在 md 报告里。
    print("")
    print("===== 摘要 =====")
    print(f"题量: {stats['total']} | 主裁判位置偏见题数: {stats['bias_count']} | 错误: {stats['errors']}")
    print(f"最终胜者(多数投票): A {stats['win_a']} | B {stats['win_b']} | 平 {stats['ties']}")
    if stats["longer_decided"] > 0:
        rate = stats["longer_wins"] / stats["longer_decided"] * 100
        print(f"更长回答胜率: {stats['longer_wins']}/{stats['longer_decided']} ({rate:.1f}%)")
    else:
        print("更长回答胜率: 无有胜负且长度不同的题")
    for j in range(len(judges)):
        model_j = judges[j][1]
        family_j = model_j.split("-")[0]
        if stats["judge_side"][j] == "":
            print(f"裁判{j + 1} {model_j}（族={family_j}，与两选手不同族）: A {stats['judge_win_a'][j]} | B {stats['judge_win_b'][j]} | 平 {stats['judge_win_tie'][j]}")
        else:
            if stats["judge_same_decided"][j] > 0:
                same_rate = stats["judge_same_wins"][j] / stats["judge_same_decided"][j] * 100
                print(f"裁判{j + 1} {model_j}（族={family_j}，与选手{stats['judge_side'][j]}同族）: A {stats['judge_win_a'][j]} | B {stats['judge_win_b'][j]} | 平 {stats['judge_win_tie'][j]} | 同族胜率 {same_rate:.1f}%")
            else:
                print(f"裁判{j + 1} {model_j}（族={family_j}，与选手{stats['judge_side'][j]}同族）: A {stats['judge_win_a'][j]} | B {stats['judge_win_b'][j]} | 平 {stats['judge_win_tie'][j]}")
    print("结果目录: " + run_dir)


def main():
    """程序入口：解析参数并执行 run()。"""
    parser = argparse.ArgumentParser(description="用裁判模型做成对比较，带位置交换，检测三大偏见")
    parser.add_argument("--max-questions", type=int, default=None, help="只跑前 N 题")
    args = parser.parse_args()
    run(args.max_questions)


if __name__ == "__main__":
    main()
