#!/usr/bin/env python3
"""Pairwise 位置偏见统计模块。

输入是逐题裁判结果，输出胜负数量、位置偏见数量与比例等汇总字典。
它位于裁判结果和 Markdown 报告之间，只做内存统计，不写文件、不调用模型。"""
def compute_stats(results, rows, judges):
    """用途：汇总胜负、位置偏见、长度偏见和同模型偏见。

    输入：results、原始 answers、judges。
    输出：返回报告使用的统计字典。
    副作用：只处理内存，不调用模型、不写文件。
    异常或失败处理：空列表返回零计数，缺字段按默认值处理。"""
    # 每个裁判的计数器用三个长度固定的列表，下标和 judges 对齐。
    judge_win_a = [0, 0, 0]
    judge_win_b = [0, 0, 0]
    judge_win_tie = [0, 0, 0]
    judge_same_decided = [0, 0, 0]
    judge_same_wins = [0, 0, 0]
    judge_side = ["", "", ""]
    win_a = 0
    win_b = 0
    ties = 0
    bias_count = 0
    errors = 0
    longer_decided = 0
    longer_wins = 0

    for idx, result in enumerate(results):
        row = rows[idx]
        # 错误题直接跳过统计。
        if result["error"] != "":
            errors = errors + 1
            continue
        # 位置偏见按主裁判统计。
        if result["judge1_position_bias"]:
            bias_count = bias_count + 1
        # 最终胜者（多数投票）。
        if result["final_winner"] == "A":
            win_a = win_a + 1
        elif result["final_winner"] == "B":
            win_b = win_b + 1
        else:
            ties = ties + 1
        # 更长回答胜率：只看有胜负且长度不同的题。
        if result["final_winner"] == "A" or result["final_winner"] == "B":
            if result["answer_a_len"] != result["answer_b_len"]:
                longer_decided = longer_decided + 1
                if result["final_winner"] == "A" and result["answer_a_len"] > result["answer_b_len"]:
                    longer_wins = longer_wins + 1
                if result["final_winner"] == "B" and result["answer_b_len"] > result["answer_a_len"]:
                    longer_wins = longer_wins + 1
        # 每个裁判的胜场 + 同族统计。
        judge_winners = [result["judge1_winner"], result["judge2_winner"], result["judge3_winner"]]
        for j in range(len(judges)):
            winner_j = judge_winners[j]
            if winner_j == "A":
                judge_win_a[j] = judge_win_a[j] + 1
            elif winner_j == "B":
                judge_win_b[j] = judge_win_b[j] + 1
            elif winner_j == "tie":
                judge_win_tie[j] = judge_win_tie[j] + 1
            # 同族判定：裁判族 == 某个选手族时，记该侧为「自己人」。
            if winner_j == "A" or winner_j == "B":
                family_j = judges[j][1].split("-")[0]
                family_a = row["model_a"].split("-")[0]
                family_b = row["model_b"].split("-")[0]
                if family_j == family_a:
                    judge_side[j] = "A"
                    judge_same_decided[j] = judge_same_decided[j] + 1
                    if winner_j == "A":
                        judge_same_wins[j] = judge_same_wins[j] + 1
                elif family_j == family_b:
                    judge_side[j] = "B"
                    judge_same_decided[j] = judge_same_decided[j] + 1
                    if winner_j == "B":
                        judge_same_wins[j] = judge_same_wins[j] + 1

    # 选手模型名从第一行取（同一次运行的选手通常不变）。
    model_a = ""
    model_b = ""
    if len(rows) > 0:
        model_a = rows[0]["model_a"]
        model_b = rows[0]["model_b"]

    return {
        "total": len(results),
        "win_a": win_a,
        "win_b": win_b,
        "ties": ties,
        "bias_count": bias_count,
        "errors": errors,
        "longer_decided": longer_decided,
        "longer_wins": longer_wins,
        "judge_win_a": judge_win_a,
        "judge_win_b": judge_win_b,
        "judge_win_tie": judge_win_tie,
        "judge_same_decided": judge_same_decided,
        "judge_same_wins": judge_same_wins,
        "judge_side": judge_side,
        "model_a": model_a,
        "model_b": model_b,
    }
