#!/usr/bin/env python3
"""用法律题集评测被测模型，按题型判分并落盘报告。

流程：
  第 1 步：读取 data/legal_questions.jsonl；
  第 2 步：逐题调被测模型（CONTESTANT_A）答题；
  第 3 步：按「判分方式」路由到规则/红线/裁判判分；
  第 4 步：写 results/<时间戳>/legal_results.jsonl + xlsx + legal_report.md。

运行:
    python run_legal_eval.py
    python run_legal_eval.py --max-questions 3
"""

import argparse
import json
import os
import sys
import time

import pandas as pd

from runner import llm_client
from metrics import legal_scorer


# 项目根目录。
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
RESULTS_DIR = os.path.join(HERE, "results")


def load_questions():
    """读取法律题集，返回题目字典列表。"""
    path = os.path.join(DATA_DIR, "legal_questions.jsonl")
    if not os.path.exists(path):
        print("[错误] 找不到题集文件：" + path, file=sys.stderr)
        sys.exit(1)
    rows = []
    with open(path, encoding="utf-8") as file_handle:
        for line in file_handle:
            line = line.strip()
            if line == "":
                continue
            rows.append(json.loads(line))
    return rows


def build_report(results):
    """按维度统计 PASS/REVIEW/REJECT，生成 Markdown 报告文本。"""
    lines = []
    lines.append("# 法律题集评测报告")
    lines.append("")
    lines.append("- 运行时间：" + time.strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("")
    lines.append("## 每题结果")
    lines.append("")
    lines.append("| 题号 | 维度 | 类型 | 判分方式 | 结论 |")
    lines.append("|---|---|---|---|---|")
    for result in results:
        cells = [
            str(result.get("id", "")),
            str(result.get("维度", "")),
            str(result.get("类型", "")),
            str(result.get("判分方式", "")),
            str(result.get("verdict", "")),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## 分维度统计")
    lines.append("")
    # 按维度汇总三种结论数量。
    by_dim = {}
    for result in results:
        dim = result.get("维度", "未知")
        if dim not in by_dim:
            by_dim[dim] = {"PASS": 0, "REVIEW": 0, "REJECT": 0}
        verdict = result.get("verdict", "")
        if verdict in by_dim[dim]:
            by_dim[dim][verdict] = by_dim[dim][verdict] + 1
    for dim in by_dim:
        counts = by_dim[dim]
        lines.append("- " + dim + "：PASS " + str(counts["PASS"]) + " / REVIEW " + str(counts["REVIEW"]) + " / REJECT " + str(counts["REJECT"]))
    return "\n".join(lines)


def run(max_questions):
    """主流程：读题、答题、判分、落盘。"""
    llm_client.load_env()
    # 被测模型读 CONTESTANT_A 配置，裁判读 JUDGE 配置。
    base_a, key_a, model_a = llm_client.read_role("CONTESTANT_A", "deepseek-v4-flash")
    client_a = llm_client.build_client(base_a, key_a)
    base_j, key_j, model_j = llm_client.read_role("JUDGE", "deepseek-v4-flash")
    client_j = llm_client.build_client(base_j, key_j)

    questions = load_questions()
    if max_questions is not None and max_questions > 0:
        questions = questions[:max_questions]

    results = []
    total = len(questions)
    for i, question in enumerate(questions, start=1):
        print("[评测] " + str(i) + "/" + str(total) + " " + question.get("id", "") + " ...", end=" ", flush=True)
        time.sleep(0.5)
        # 被测模型答题。
        answer_result = llm_client.call_model(client_a, model_a, question.get("问题", ""), 0, 8192)
        answer = answer_result[0]
        # 判分。
        scoring = legal_scorer.score_one(question, answer, client_j, model_j)
        row = {
            "id": question.get("id", ""),
            "维度": question.get("维度", ""),
            "类型": question.get("类型", ""),
            "问题": question.get("问题", ""),
            "model_answer": answer,
            "判分方式": question.get("判分方式", ""),
            "verdict": scoring.get("verdict", ""),
            "必答点命中": scoring.get("必答点命中", 0),
            "必答点总数": scoring.get("必答点总数", 0),
            "扣分项命中": scoring.get("扣分项命中", 0),
            "judge_verdict": scoring.get("judge_verdict", ""),
            "judge_reason": scoring.get("judge_reason", ""),
            "reason": scoring.get("reason", ""),
        }
        results.append(row)
        print(row["verdict"])

    # 写结果到时间戳目录。
    stamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(RESULTS_DIR, stamp)
    os.makedirs(run_dir, exist_ok=True)
    jsonl_path = os.path.join(run_dir, "legal_results.jsonl")
    xlsx_path = os.path.join(run_dir, "legal_results.xlsx")
    md_path = os.path.join(run_dir, "legal_report.md")
    with open(jsonl_path, "w", encoding="utf-8") as file_handle:
        for row in results:
            file_handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    dataframe = pd.DataFrame(results)
    dataframe.to_excel(xlsx_path, sheet_name="legal_results", index=False)
    markdown = build_report(results)
    with open(md_path, "w", encoding="utf-8") as file_handle:
        file_handle.write(markdown)

    # 控制台简报。
    print("")
    print("===== 摘要 =====")
    print("题量：" + str(total))
    print("结果目录：" + run_dir)


def main():
    """程序入口：解析参数并执行 run()。"""
    parser = argparse.ArgumentParser(description="用法律题集评测模型")
    parser.add_argument("--max-questions", type=int, default=None, help="只跑前 N 题")
    args = parser.parse_args()
    run(args.max_questions)


if __name__ == "__main__":
    main()
