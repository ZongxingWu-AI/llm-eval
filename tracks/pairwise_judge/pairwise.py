"""项目模块：tracks/pairwise_judge/pairwise.py。

本文件属于三条评测线或公共工具层的一部分，负责完成本文件名对应的处理步骤。输入来自上游函数或数据目录，输出返回给下游函数或写入对应结果目录。

项目位置：tracks/pairwise_judge/pairwise.py。
主要用途：开放题 LLM-as-Judge 评测线，负责生成回答、位置交换裁判、多裁判统计和报告。
输入：输入来自本评测线的 data 目录、裁判 Prompt 和公共模型客户端。
输出：输出写入本评测线的 results 目录，供偏见分析和报告阅读。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：生成和裁判模块会调用模型；统计和报告模块只处理内存数据或写结果文件。
"""

from core import llm_client
from core.json_utils import parse_json_object
from tracks.pairwise_judge import judge_prompt


JUDGE_TEMPERATURE = 0
JUDGE_MAX_TOKENS = 8192


def parse_judge_json(text: str) -> dict | None:
    """解析裁判模型输出并要求得到 JSON 对象。解析失败时返回 None，避免单条坏结果中断整批评测。"""

    try:
        return parse_json_object(text)
    except ValueError:
        return None


def normalize_winner(raw) -> str | None:
    """把裁判输出的 winner 字段统一成 ``A``、``B`` 或 ``tie``。

    输入可能是大小写混合的字符串或空值；输出供后续两轮位置映射使用。
    非法标签返回 ``None``，函数只处理内存值，不调用模型、不写文件。
    """

    if raw is None:
        return None
    winner = str(raw).strip().upper()
    if winner in {"A", "B"}:
        return winner
    if winner == "TIE":
        return "tie"
    return None


def parse_score_total(score_dict) -> int:
    """完成当前模块中的一个处理步骤。

参数：score_dict。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

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
    """为同一文件中的公开流程提供一个小而明确的辅助步骤。

参数：reason。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    return {"judge_winner": "", "position_bias": False, "round1_winner": "", "round2_winner": "",
            "score_a_total": 0, "score_b_total": 0, "reason_1": "", "reason_2": "", "error": reason}


def judge_one(row: dict, client, model: str) -> dict:
    """对一条开放题回答执行两轮位置交换裁判。

    第一轮把原始选手 A/B 放在 A/B 位置，第二轮交换回答位置；第二轮的标签会
    映射回原始选手后再比较。若两轮映射结果冲突，返回 ``tie`` 并将
    ``position_bias`` 设为 ``True``。例如第二轮判定位置 A 胜出时，映射后的胜者
    是原始选手 B，而不是简单记录为 A。函数会调用模型，但不写文件。
    """

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
    """汇总多个裁判的胜者标签。

    输入是 ``A``、``B``、``tie`` 组成的列表；只有某一标签严格多于另外两类
    时才返回该标签，否则返回 ``tie``。例如 ``["A", "A", "B"]`` 返回 ``A``，
    ``["A", "B", "tie"]`` 返回 ``tie``。
    """

    counts = {"A": winners.count("A"), "B": winners.count("B"), "tie": winners.count("tie")}
    if counts["A"] > counts["B"] and counts["A"] > counts["tie"]:
        return "A"
    if counts["B"] > counts["A"] and counts["B"] > counts["tie"]:
        return "B"
    return "tie"
