#!/usr/bin/env python3
"""用两个选手模型对开放题各生成一版回答，供裁判评分。

流程：
  第 1 步：读取题集 data/judge_questions.jsonl；
  第 2 步：对每题分别调用选手 A、选手 B 各生成一版回答；
  第 3 步：把两版回答写成 data/judge_answers.jsonl。
"""

import argparse
import json
import os
import sys
import time

from runner import llm_client  # 统一模型客户端：读配置、调模型


# 脚本所在目录，用来拼题集和回答文件的路径。
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

# 选手生成回答用较高温度，让两个选手的输出更丰富、更有差异。
CONTESTANT_TEMPERATURE = 0.7
# 思考类模型需要较大 max_tokens，避免答案被思考过程截断。
CONTESTANT_MAX_TOKENS = 8192


def load_questions():
    """读取题集文件，返回题目字典列表。

    输入：无。
    输出：题目列表，每条例如
      {"id": "q01", "question": "用 200 字以内，向完全不懂技术的人介绍什么是「大模型评测」。"}
    """
    # 运行前：还没有读文件。
    # 运行后：path 变成题集文件路径。
    path = os.path.join(DATA_DIR, "judge_questions.jsonl")
    if not os.path.exists(path):
        print("[错误] 找不到题集文件：" + path, file=sys.stderr)
        sys.exit(1)

    # 运行前：questions 是空列表。
    questions = []
    with open(path, encoding="utf-8") as file_handle:
        for line in file_handle:
            line = line.strip()
            if line == "":
                continue
            # 运行后：question 变成解析好的字典。
            question = json.loads(line)
            questions.append(question)
    # 运行后：questions 变成 5 条题目的列表。
    return questions


def generate(max_questions):
    """主流程：逐题调用两个选手生成回答并落盘。"""
    llm_client.load_env()

    # 运行前：两个选手还没有配置。
    # 运行后：拿到各自的 (base_url, api_key, model)。
    base_a, key_a, model_a = llm_client.read_role("CONTESTANT_A", "deepseek-v4-flash")
    base_b, key_b, model_b = llm_client.read_role("CONTESTANT_B", "deepseek-v4-pro")
    # 运行后：client_a、client_b 是两个可独立发请求的客户端对象。
    client_a = llm_client.build_client(base_a, key_a)
    client_b = llm_client.build_client(base_b, key_b)

    questions = load_questions()
    # 运行前：questions 是全部 5 题。
    # 运行后：questions 变成前 N 题（传了 --max-questions 时）。
    if max_questions is not None and max_questions > 0:
        questions = questions[:max_questions]

    rows = []
    total = len(questions)
    for i, q in enumerate(questions, start=1):
        print("[选手] " + str(i) + "/" + str(total) + " " + q["id"] + " ...", end=" ", flush=True)
        try:
            # 两题之间停 0.5 秒控速。
            time.sleep(0.5)
            # 运行前：q["question"] 是题目文本。
            # 运行后：result_a 是 (文本, 延迟, token, finish_reason) 四元组。
            result_a = llm_client.call_model(client_a, model_a, q["question"], CONTESTANT_TEMPERATURE, CONTESTANT_MAX_TOKENS)
            # 运行后：answer_a 只取四元组的第 0 项——回答文本。
            answer_a = result_a[0]
            time.sleep(0.5)
            result_b = llm_client.call_model(client_b, model_b, q["question"], CONTESTANT_TEMPERATURE, CONTESTANT_MAX_TOKENS)
            answer_b = result_b[0]
            # 运行前：answer_a / answer_b 是两版回答文本。
            # 运行后：row 变成这道题的结果字典。
            row = {
                "id": q["id"],
                "question": q["question"],
                "answer_a": answer_a,
                "model_a": model_a,
                "answer_b": answer_b,
                "model_b": model_b,
                "error": "",
            }
            print("OK (A=" + str(len(answer_a)) + "字, B=" + str(len(answer_b)) + "字)")
        except Exception as exc:
            # 生成失败时标记 error，不中断整个流程。
            row = {
                "id": q["id"],
                "question": q["question"],
                "answer_a": "",
                "model_a": model_a,
                "answer_b": "",
                "model_b": model_b,
                "error": str(exc),
            }
            print("ERROR: " + str(exc))
        rows.append(row)

    # 写回答文件：data/judge_answers.jsonl。
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    out_path = os.path.join(DATA_DIR, "judge_answers.jsonl")
    with open(out_path, "w", encoding="utf-8") as file_handle:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False)
            file_handle.write(line + "\n")
    print("完成：" + out_path + "，共 " + str(len(rows)) + " 题")
    # 顺手把 jsonl 同步成 Excel；失败只提示，不影响回答生成。
    try:
        import to_excel
        to_excel.convert_all()
    except Exception as exc:
        print("[提示] 刷新 Excel 失败（不影响回答生成）：" + str(exc), file=sys.stderr)


def main():
    """程序入口：解析参数并执行 generate()。"""
    parser = argparse.ArgumentParser(description="用两个选手模型生成开放题回答")
    parser.add_argument("--max-questions", type=int, default=None, help="只跑前 N 题")
    args = parser.parse_args()
    generate(args.max_questions)


if __name__ == "__main__":
    main()
