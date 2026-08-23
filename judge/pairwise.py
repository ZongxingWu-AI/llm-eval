#!/usr/bin/env python3
"""成对比较的核心逻辑：解析裁判输出、判定胜负、多数投票。

这里不碰文件读写，只做纯计算，方便复用和单独测试。
"""

import json  # 用来把裁判返回的 JSON 文本解析成字典

from runner import llm_client          # 调用模型
from prompts import judge_prompt       # 拼裁判提示词


# 裁判要可复现，所以 temperature 用 0（贪婪解码）。
JUDGE_TEMPERATURE = 0
# 裁判要输出分析 + 分数 + 结论，留足 token。
JUDGE_MAX_TOKENS = 8192


def parse_judge_json(text):
    """把裁判返回的文本解析成字典；解析失败返回 None。

    输入：裁判返回的原始文本（可能带 ```json 代码围栏）。
    输出：字典，例如 {"analysis": "……", "winner": "A"}；解析失败返回 None。
    """
    # 运行前：text 可能是 "```json\n{...}\n```" 这种带围栏的文本。
    text = text.strip()
    if text.startswith("```"):
        # 运行前：lines 是按换行拆开的列表，例如 ["```json", "{...}", "```"]。
        lines = text.split("\n")
        # 去掉第一行 ```json。
        if len(lines) > 0 and lines[0].startswith("```"):
            lines = lines[1:]
        # 去掉最后一行 ```。
        if len(lines) > 0 and lines[-1].strip() == "```":
            lines = lines[:-1]
        # 运行后：text 变成剥掉围栏后的纯 JSON 文本。
        text = "\n".join(lines)
    try:
        # 运行后：data 变成字典，例如 {"analysis": "...", "winner": "A"}。
        data = json.loads(text)
    except Exception:
        return None
    return data


def normalize_winner(raw):
    """把裁判给的 winner 归一成 "A"、"B"、"tie"；非法值返回 None。

    输入：裁判输出里的 winner 字段，可能是 "a"、"A"、"tie"、"TIE" 或乱写的值。
    输出："A" / "B" / "tie"；不认识的返回 None。
    """
    if raw is None:
        return None
    # 运行前：raw 可能是 "a"、"TIE"、"tie"、"X" 或 None。
    # 运行后：winner 变成去掉空白、全大写的字符串，例如 "A"、"TIE"、"X"。
    winner = str(raw).strip().upper()
    if winner == "A":
        return "A"
    if winner == "B":
        return "B"
    if winner == "TIE":
        return "tie"
    return None


def parse_score_total(score_dict):
    """把裁判给的某一侧分数字典加起来，得到总分。

    输入：score_dict，例如
      {"准确性": 8, "相关性": 7, "完整性": 6, "表达力": 9, "实用性": 8}。
    输出：总分（整数），例如 38；字典缺失或分数不是数字时按 0 处理。
    """
    # 运行前：score_dict 可能是上面的字典，也可能是 None。
    # 运行后：total 变成 5 个维度分数之和。
    if score_dict is None:
        return 0
    total = 0
    for key in score_dict:
        value = score_dict[key]
        try:
            total = total + int(value)
        except Exception:
            # 某个维度不是数字时忽略它，不影响其他维度。
            total = total + 0
    return total


def judge_one(row, client, model):
    """用单个裁判对一题做两轮成对比较，返回该裁判的判定字典。

    输入：
      row    是回答文件里的一行（含 question / answer_a / answer_b）；
      client 是该裁判的客户端；
      model  是该裁判的模型名。
    输出字典字段：
      judge_winner   该裁判判定谁赢："A"、"B" 或 "tie"；
      position_bias  两轮结果相反时为 True；
      round1_winner  第 1 轮（未交换）判的选手；
      round2_winner  第 2 轮（已交换）判的选手；
      score_a_total  第 1 轮里选手 A 的 5 维总分；
      score_b_total  第 1 轮里选手 B 的 5 维总分；
      reason_1       第 1 轮的分析文本；
      reason_2       第 2 轮的分析文本；
      error          解析失败时给原因，成功为空字符串。
    """
    # 运行前：row 是一个字典，例如
    #   {"id": "q01", "question": "用 200 字以内介绍大模型评测",
    #    "answer_a": "选手A的回答……", "model_a": "glm-5.2",
    #    "answer_b": "选手B的回答……", "model_b": "qwen3.7-plus", "error": ""}
    # 运行后：question / answer_a / answer_b 三个变量被取出来。
    question = row["question"]
    answer_a = row["answer_a"]
    answer_b = row["answer_b"]

    # 第 1 轮：回答A=选手A(answer_a)，回答B=选手B(answer_b)。
    prompt1 = judge_prompt.build_judge_prompt(question, answer_a, answer_b)
    result1 = llm_client.call_model(client, model, prompt1, JUDGE_TEMPERATURE, JUDGE_MAX_TOKENS)
    raw1 = result1[0]
    # 运行后：data1 是第 1 轮裁判返回的 JSON 字典，例如 {"analysis": "……", "winner": "A"}。
    data1 = parse_judge_json(raw1)

    # 第 2 轮：交换位置，回答A=选手B(answer_b)，回答B=选手A(answer_a)。
    prompt2 = judge_prompt.build_judge_prompt(question, answer_b, answer_a)
    result2 = llm_client.call_model(client, model, prompt2, JUDGE_TEMPERATURE, JUDGE_MAX_TOKENS)
    raw2 = result2[0]
    # 运行后：data2 是第 2 轮裁判返回的 JSON 字典。
    data2 = parse_judge_json(raw2)

    # 解析失败直接记 error，不计入统计。
    if data1 is None or data2 is None:
        return {
            "judge_winner": "",
            "position_bias": False,
            "round1_winner": "",
            "round2_winner": "",
            "score_a_total": 0,
            "score_b_total": 0,
            "reason_1": "",
            "reason_2": "",
            "error": "裁判输出无法解析",
        }

    # 运行后：r1_label / r2_label 变成归一化后的标签，例如 "A"、"B"、"tie"。
    r1_label = normalize_winner(data1.get("winner", ""))
    r2_label = normalize_winner(data2.get("winner", ""))
    if r1_label is None or r2_label is None:
        return {
            "judge_winner": "",
            "position_bias": False,
            "round1_winner": "",
            "round2_winner": "",
            "score_a_total": 0,
            "score_b_total": 0,
            "reason_1": "",
            "reason_2": "",
            "error": "winner 字段非法",
        }

    # 把「标签 A/B」换算成「选手 A/B」。
    # 第 1 轮没交换：标签 A = 选手A，标签 B = 选手B。
    if r1_label == "A":
        r1_contestant = "A"
    elif r1_label == "B":
        r1_contestant = "B"
    else:
        r1_contestant = "tie"
    # 第 2 轮交换了：标签 A = 选手B，标签 B = 选手A。
    if r2_label == "A":
        r2_contestant = "B"
    elif r2_label == "B":
        r2_contestant = "A"
    else:
        r2_contestant = "tie"

    # 一致性判定分三种情况：
    # 1) 两轮都指向同一个选手：一致，该选手胜；
    # 2) 两轮一平一胜：不算位置偏见，算弱胜（以非平局那轮为准）；
    # 3) 两轮分别指向不同选手（A vs B 互换）：真正的「位置偏见」，判平。
    position_bias = False
    judge_winner = "tie"
    if r1_contestant == r2_contestant:
        judge_winner = r1_contestant
    elif r1_contestant == "tie":
        judge_winner = r2_contestant
    elif r2_contestant == "tie":
        judge_winner = r1_contestant
    else:
        position_bias = True
        judge_winner = "tie"

    # 运行前：data1 里有 score_a / score_b 两个分数字典。
    # 运行后：score_a_total / score_b_total 变成两个总分，例如 38 和 35。
    score_a_total = parse_score_total(data1.get("score_a"))
    score_b_total = parse_score_total(data1.get("score_b"))

    return {
        "judge_winner": judge_winner,
        "position_bias": position_bias,
        "round1_winner": r1_contestant,
        "round2_winner": r2_contestant,
        "score_a_total": score_a_total,
        "score_b_total": score_b_total,
        "reason_1": data1.get("analysis", ""),
        "reason_2": data2.get("analysis", ""),
        "error": "",
    }


def majority_winner(winners):
    """对多个裁判的判定做多数投票。

    输入：winners 是裁判判定的列表，例如 ["A", "B", "A"]。
    输出："A" / "B" / "tie"。
    规则：A 或 B 谁的票数严格最多且超过平局票数就赢，否则判平。
    """
    # 运行前：winners 是多个裁判的判定。
    # 运行后：count_a / count_b / count_tie 变成各自的票数。
    count_a = 0
    count_b = 0
    count_tie = 0
    for winner in winners:
        if winner == "A":
            count_a = count_a + 1
        elif winner == "B":
            count_b = count_b + 1
        else:
            count_tie = count_tie + 1
    if count_a > count_b and count_a > count_tie:
        return "A"
    if count_b > count_a and count_b > count_tie:
        return "B"
    return "tie"
