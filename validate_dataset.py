#!/usr/bin/env python3
"""对题集做规则校验，输出 data/validation_report.md。

规则校验不调大模型：检查字段、维度、类型、必答点、答案泄露、重复题、负向题占比。
加 --llm-check 参数时，才用校验 prompt 让模型做语义复核（默认关，省 token）。

运行:
    python validate_dataset.py
    python validate_dataset.py --llm-check
"""

import argparse
import json
import os

from runner import llm_client
from prompts import loader
from judge import pairwise  # 复用它的 JSON 解析函数


# 项目根目录。
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
DIMENSIONS_PATH = os.path.join(DATA_DIR, "legal_dimensions.json")
QUESTIONS_PATH = os.path.join(DATA_DIR, "legal_questions.jsonl")


def load_dimensions():
    """读取维度表，返回列表。"""
    with open(DIMENSIONS_PATH, encoding="utf-8") as file_handle:
        return json.load(file_handle)


def load_questions():
    """读取题集，返回题目字典列表。"""
    rows = []
    if not os.path.exists(QUESTIONS_PATH):
        print("[错误] 找不到题集文件：" + QUESTIONS_PATH)
        return rows
    with open(QUESTIONS_PATH, encoding="utf-8") as file_handle:
        for line in file_handle:
            line = line.strip()
            if line == "":
                continue
            rows.append(json.loads(line))
    return rows


def check_row(row, dimensions):
    """返回一道题的所有问题列表（空列表表示通过）。"""
    issues = []
    # 必填字段检查。
    for field in ["id", "维度", "类型", "问题", "标准答案要点", "评分细则", "判分方式"]:
        value = row.get(field)
        if value is None or value == "":
            issues.append("缺字段 " + field)
    # 维度是否在维度表里。
    if row.get("维度") not in dimensions:
        issues.append("维度非法：" + str(row.get("维度")))
    # 类型只能是正向或负向。
    if row.get("类型") not in ["正向", "负向"]:
        issues.append("类型非法：" + str(row.get("类型")))
    # 评分细则的必答点不能为空。
    rubric = row.get("评分细则")
    if rubric is None:
        rubric = {}
    required = rubric.get("必答点", [])
    if len(required) == 0:
        issues.append("评分细则.必答点 为空")
    # 判分方式合法。
    if row.get("判分方式") not in ["规则", "红线", "裁判"]:
        issues.append("判分方式非法：" + str(row.get("判分方式")))
    # 答案泄露检查：标准答案要点或必答点里的关键词，不能直接出现在问题里。
    question_text = row.get("问题", "")
    keys = []
    for point in row.get("标准答案要点", []):
        keys.append(point)
    for point in required:
        keys.append(point)
    for key in keys:
        key = str(key).strip()
        if key != "" and key in question_text:
            issues.append("疑似答案泄露：" + key)
    return issues


def llm_check(questions, client, model):
    """让模型逐题做语义复核，返回 [(题号, 问题列表)]。"""
    template = loader.load_template("legal_validator_prompt.md")
    extra = []
    for question in questions:
        item_text = json.dumps(question, ensure_ascii=False)
        prompt = loader.render(template, {"item": item_text})
        result = llm_client.call_model(client, model, prompt, 0, 8192)
        raw = result[0]
        data = pairwise.parse_judge_json(raw)
        if data is None:
            extra.append((question.get("id", ""), ["模型复核：输出无法解析"]))
            continue
        passed = data.get("pass")
        if passed is False:
            extra.append((question.get("id", ""), data.get("issues", [])))
    return extra


def main():
    """程序入口：规则校验 + 可选模型复核，写校验报告。"""
    parser = argparse.ArgumentParser(description="校验法律题集")
    parser.add_argument("--llm-check", action="store_true", help="用模型做语义复核（默认关）")
    args = parser.parse_args()

    dimensions = load_dimensions()
    questions = load_questions()

    # 逐题检查 + 重复题检测 + 负向题占比。
    seen_questions = {}
    negative_count = 0
    lines = []
    lines.append("# 法律题集校验报告")
    lines.append("")
    for question in questions:
        qid = question.get("id", "")
        issues = check_row(question, dimensions)
        question_text = question.get("问题", "")
        if question_text != "" and question_text in seen_questions:
            issues.append("与 " + seen_questions[question_text] + " 重复")
        else:
            seen_questions[question_text] = qid
        if question.get("类型") == "负向":
            negative_count = negative_count + 1
        if len(issues) == 0:
            lines.append("- " + qid + "：通过")
        else:
            lines.append("- " + qid + "：不通过 → " + "；".join(issues))

    # 汇总统计。
    total = len(questions)
    lines.append("")
    lines.append("## 汇总")
    lines.append("- 题目总数：" + str(total))
    lines.append("- 负向题数：" + str(negative_count))
    if total > 0:
        ratio = negative_count / total * 100
        lines.append("- 负向题占比：" + format(ratio, ".1f") + "%（建议 ≥ 20%）")

    # 可选：模型语义复核。
    if args.llm_check:
        llm_client.load_env()
        base, key, model = llm_client.read_role("JUDGE", "deepseek-v4-flash")
        client = llm_client.build_client(base, key)
        extra = llm_check(questions, client, model)
        lines.append("")
        lines.append("## 模型语义复核")
        for qid, issues in extra:
            lines.append("- " + qid + "：" + "；".join(issues))

    report_path = os.path.join(DATA_DIR, "validation_report.md")
    with open(report_path, "w", encoding="utf-8") as file_handle:
        file_handle.write("\n".join(lines))
    print("完成：" + report_path)


if __name__ == "__main__":
    main()
