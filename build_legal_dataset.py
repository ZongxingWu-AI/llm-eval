#!/usr/bin/env python3
"""把人工出题的草稿组装成正式题集 data/legal_questions.jsonl。

流程：
  第 1 步：读取 data/drafts/legal_drafts.jsonl；
  第 2 步：校验草稿最小字段，缺字段的跳过并提示；
  第 3 步：补 id、created_at、version 后写入正式题集。

运行:
    python build_legal_dataset.py
    python build_legal_dataset.py --show-sample
"""

import argparse
import json
import os
import sys
import time


# 项目根目录。
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

# 一道题至少要有的字段。
REQUIRED_FIELDS = ["维度", "类型", "问题", "标准答案要点", "评分细则", "判分方式"]


def load_drafts():
    """读取人工草稿文件，返回草稿字典列表。"""
    path = os.path.join(DATA_DIR, "drafts", "legal_drafts.jsonl")
    if not os.path.exists(path):
        print("[错误] 找不到草稿文件：" + path, file=sys.stderr)
        sys.exit(1)
    rows = []
    with open(path, encoding="utf-8") as file_handle:
        for line in file_handle:
            line = line.strip()
            if line == "":
                continue
            rows.append(json.loads(line))
    return rows


def is_empty(value):
    """判断一个值是否为空（None、空字符串或空列表都算空）。"""
    if value is None:
        return True
    if value == "":
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    return False


def build(drafts):
    """校验草稿并补 id/时间戳/版本，返回正式题集列表。"""
    questions = []
    index = 0
    for draft in drafts:
        # AI 起草的草稿带「待审」标记，默认不进正式题集；
        # 人工审完把标记改成 false（或删掉该字段）后，build 才会纳入。
        if draft.get("待审") is True:
            continue
        missing = []
        for field in REQUIRED_FIELDS:
            if is_empty(draft.get(field)):
                missing.append(field)
        if len(missing) > 0:
            preview = json.dumps(draft, ensure_ascii=False)[:60]
            print("[跳过] 缺字段 " + "、".join(missing) + "：" + preview)
            continue
        index = index + 1
        question = dict(draft)
        question["id"] = "legal_" + str(index).zfill(4)
        question["created_at"] = time.strftime("%Y-%m-%d")
        question["version"] = "1.0"
        questions.append(question)
    return questions


def main():
    """程序入口：读草稿、组装、写题集，可选打印示例。"""
    parser = argparse.ArgumentParser(description="组装法律题集")
    parser.add_argument("--show-sample", action="store_true", help="打印第一题完整 JSON")
    args = parser.parse_args()

    drafts = load_drafts()
    # 运行前：drafts 是人工写的草稿列表。
    # 运行后：questions 变成带 id/created_at/version 的正式题目列表。
    questions = build(drafts)
    out_path = os.path.join(DATA_DIR, "legal_questions.jsonl")
    with open(out_path, "w", encoding="utf-8") as file_handle:
        for question in questions:
            line = json.dumps(question, ensure_ascii=False)
            file_handle.write(line + "\n")
    print("完成：" + out_path + "，共 " + str(len(questions)) + " 题")
    if args.show_sample and len(questions) > 0:
        print("第一题示例：")
        print(json.dumps(questions[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
