"""Pairwise 双轮裁判核心模块。

输入是问题、原始选手 A/B 的回答、裁判客户端和模型名。
输出两轮位置交换后的原始选手胜负映射、分数、理由、位置偏见和错误信息。
judge_one 会调用裁判模型，但本模块不直接写结果文件。"""

from core import llm_client
from core.json_utils import parse_json_object
from tracks.pairwise_judge import judge_prompt


JUDGE_TEMPERATURE = 0
JUDGE_MAX_TOKENS = 8192


def parse_judge_json(text: str) -> dict | None:
    """用途：解析裁判模型输出的 JSON 对象。

    输入：text：裁判原始文本。
    输出：成功返回 dict，失败返回 None。
    副作用：只处理内存。
    异常或失败处理：公共解析器抛 ValueError 时转换为 None。"""

    try:
        return parse_json_object(text)
    except ValueError:
        return None


def normalize_winner(raw) -> str | None:
    """用途：把 winner 多种写法统一为 A、B 或 tie。

    输入：value：任意 winner 值。
    输出：返回 A、B、tie 或 None。
    副作用：只处理内存。
    异常或失败处理：未知标签返回 None。"""

    if raw is None:
        return None
    winner = str(raw).strip().upper()
    if winner in {"A", "B"}:
        return winner
    if winner == "TIE":
        return "tie"
    return None


def parse_score_total(score_dict) -> int:
    """用途：把 score_a 或 score_b 的各维分值求和。

    输入：score_dict：维度到分值的字典。
    输出：返回整数总分。
    运行前数据形态：分值可能是数字或数字字符串。
    运行后数据变化：逐项 int 转换后累加。
    副作用：只处理内存。
    异常或失败处理：非字典返回 0，非法分值跳过。
    最小示例：{"x":5,"y":"4"} 返回 9。"""

    if not isinstance(score_dict, dict):
        return 0
    total = 0
    for value in score_dict.values():
        try:
            total += int(value)
        except (TypeError, ValueError):
            pass
    return total


def _error(reason: str) -> dict:
    """用途：构造字段完整的 Pairwise 失败结果。

    输入：reason：失败原因。
    输出：返回带默认胜者、分数、理由和 error 的字典。
    副作用：只处理内存。
    异常或失败处理：空 reason 也返回完整结构。"""

    return {"judge_winner": "", "position_bias": False, "round1_winner": "", "round2_winner": "",
            "score_a_total": 0, "score_b_total": 0, "reason_1": "", "reason_2": "", "error": reason}


def judge_one(row: dict, client, model: str) -> dict:
    """用途：对一题回答执行两轮位置交换裁判并映射回原始选手。

    输入：row：question/answer_a/answer_b；client/model。
    输出：返回最终胜者、两轮胜者、分数、理由、位置偏见和 error。
    运行前数据形态：第二轮交换 A/B 展示位置。
    运行后数据变化：第二轮位置标签反向映射后再与第一轮合并。
    副作用：会调用模型两次；不写文件。
    异常或失败处理：JSON 或 winner 非法时返回错误结构；冲突时返回 tie。
    最小示例：第二轮位置 A 胜表示原始选手 B 胜。"""

    question, answer_a, answer_b = row["question"], row["answer_a"], row["answer_b"]
    raw1 = llm_client.call_model(
        client, model, judge_prompt.build_judge_prompt(question, answer_a, answer_b),
        JUDGE_TEMPERATURE, JUDGE_MAX_TOKENS,
    )[0]
    raw2 = llm_client.call_model(
        client, model, judge_prompt.build_judge_prompt(question, answer_b, answer_a),
        JUDGE_TEMPERATURE, JUDGE_MAX_TOKENS,
    )[0]
    data1, data2 = parse_judge_json(raw1), parse_judge_json(raw2)
    if data1 is None or data2 is None:
        return _error("裁判输出无法解析")
    label1, label2 = normalize_winner(data1.get("winner")), normalize_winner(data2.get("winner"))
    if label1 is None or label2 is None:
        return _error("winner 字段非法")
    contestant1 = label1
    if label2 == "A":
        contestant2 = "B"
    elif label2 == "B":
        contestant2 = "A"
    else:
        contestant2 = "tie"
    position_bias = False
    if contestant1 == contestant2:
        winner = contestant1
    elif contestant1 == "tie":
        winner = contestant2
    elif contestant2 == "tie":
        winner = contestant1
    else:
        winner, position_bias = "tie", True
    return {
        "judge_winner": winner, "position_bias": position_bias,
        "round1_winner": contestant1, "round2_winner": contestant2,
        "score_a_total": parse_score_total(data1.get("score_a")),
        "score_b_total": parse_score_total(data1.get("score_b")),
        "reason_1": data1.get("analysis", ""), "reason_2": data2.get("analysis", ""), "error": "",
    }


def majority_winner(winners: list[str]) -> str:
    """用途：对多个裁判胜者做严格多数投票。

    输入：winners：A、B、tie 列表。
    输出：唯一严格多数时返回该标签，否则 tie。
    运行前数据形态：输入为映射后的原始选手标签。
    运行后数据变化：分别计数并比较三类。
    副作用：只处理内存。
    异常或失败处理：空列表或并列返回 tie。
    最小示例：[A,A,B] 返回 A。"""

    counts = {"A": winners.count("A"), "B": winners.count("B"), "tie": winners.count("tie")}
    if counts["A"] > counts["B"] and counts["A"] > counts["tie"]:
        return "A"
    if counts["B"] > counts["A"] and counts["B"] > counts["tie"]:
        return "B"
    return "tie"
