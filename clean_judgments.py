#!/usr/bin/env python3
"""清洗管道：把 data/raw 下的判决书 txt/md 逐份解析成结构化案情。

流程：
  第 1 步：列出 data/raw 下所有 .txt/.md 文件；
  第 2 步：跳过已经处理过的文件（幂等，可反复运行）；
  第 3 步：逐份提取案号、案情、脱敏、浓缩；
  第 4 步：追加写入 data/cleaned/cleaned_judgments.jsonl。

运行:
    python clean_judgments.py
"""

import argparse
import json
import os
import re
import time


# 项目根目录，下面拼 data/raw、data/cleaned。
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
CLEANED_DIR = os.path.join(DATA_DIR, "cleaned")

# 案情段浓缩到多少字以内。
MAX_FACTS_LEN = 300


def list_raw_files(raw_dir):
    """列出 raw 目录下所有 txt/md 文件，返回文件名列表（已排序）。"""
    names = os.listdir(raw_dir)
    files = []
    for name in names:
        lower = name.lower()
        # README 不是判决书，跳过。
        if lower == "readme.md" or lower.startswith("readme."):
            continue
        if lower.endswith(".txt") or lower.endswith(".md"):
            files.append(name)
    files.sort()
    return files


def load_processed(output_path):
    """读取已清洗结果，返回 (已处理文件集合, 已有行列表)。"""
    processed = set()
    rows = []
    if not os.path.exists(output_path):
        return processed, rows
    with open(output_path, encoding="utf-8") as file_handle:
        for line in file_handle:
            line = line.strip()
            if line == "":
                continue
            row = json.loads(line)
            rows.append(row)
            source = row.get("source_file", "")
            if source != "":
                processed.add(source)
    return processed, rows


def extract_case_no(text):
    """从判决书里提取案号，例如（2024）京0105民初12345号。"""
    match = re.search(r"（\d{4}）[^\n，。]{2,25}号", text)
    if match is None:
        return ""
    return match.group(0)


def extract_name(text, label):
    """提取 label（如「原告」）后面的当事人姓名。"""
    match = re.search(label + r"[:：]?\s*([^\n，。]{1,5})", text)
    if match is None:
        return ""
    return match.group(1).strip()


def extract_facts(text):
    """提取「经审理查明」到「本院认为」之间的案情段。"""
    start_marker = "经审理查明"
    end_marker = "本院认为"
    start = text.find(start_marker)
    if start == -1:
        # 找不到标志词时，退而求其次取全文前 600 字作为案情。
        return text[:600]
    start = start + len(start_marker)
    end = text.find(end_marker, start)
    if end == -1:
        segment = text[start:]
    else:
        segment = text[start:end]
    return segment


def anonymize(text, name_a, name_b):
    """把原告、被告姓名替换成甲/乙，做脱敏。"""
    result = text
    if name_a != "":
        result = result.replace("原告" + name_a, "原告甲")
        result = result.replace(name_a, "甲")
    if name_b != "":
        result = result.replace("被告" + name_b, "被告乙")
        result = result.replace(name_b, "乙")
    return result


def summarize(text, max_len):
    """把案情段浓缩到 max_len 字以内。"""
    text = text.strip()
    # 去掉开头多余的冒号/逗号等标点。
    while len(text) > 0 and text[0] in "：:，,。；;\n\t ":
        text = text[1:]
    if len(text) <= max_len:
        return text
    return text[:max_len] + "……"


def clean_one(source_file, text, index):
    """把一份判决书清洗成一行结构化数据。

    输入：source_file 文件名；text 判决书全文；index 用于生成序号。
    输出：一个字典，例如
      {"id": "case_0001", "source_file": "样例判决书.txt",
       "案号": "（2024）京0105民初12345号", "当事人": "原告甲、被告乙",
       "案情": "张三于2023年3月入职……", "引用法条": "", "cleaned_at": "……"}
    """
    case_no = extract_case_no(text)
    name_a = extract_name(text, "原告")
    name_b = extract_name(text, "被告")
    # 运行前：facts 是「经审理查明」到「本院认为」之间的原始案情。
    facts = extract_facts(text)
    # 运行后：facts 里的当事人姓名被替换成甲/乙，长度被压到 300 字以内。
    facts = anonymize(facts, name_a, name_b)
    facts = summarize(facts, MAX_FACTS_LEN)
    # 当事人字段也存脱敏后的写法。
    parties = ""
    if name_a != "":
        parties = parties + "原告甲"
    if name_b != "":
        if parties != "":
            parties = parties + "、"
        parties = parties + "被告乙"
    row = {
        "id": "case_" + str(index).zfill(4),
        "source_file": source_file,
        "案号": case_no,
        "当事人": parties,
        "案情": facts,
        "引用法条": "",
        "cleaned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return row


def main():
    """程序入口：遍历 raw 文件，跳过已处理，逐份清洗并追加写结果。"""
    parser = argparse.ArgumentParser(description="清洗 data/raw 下的判决书")
    args = parser.parse_args()

    # 确保 raw 和 cleaned 目录存在。
    if not os.path.exists(RAW_DIR):
        os.makedirs(RAW_DIR)
    if not os.path.exists(CLEANED_DIR):
        os.makedirs(CLEANED_DIR)
    output_path = os.path.join(CLEANED_DIR, "cleaned_judgments.jsonl")

    # 运行前：processed 是已经处理过的源文件名集合。
    # 运行后：用于跳过重复文件，保证幂等。
    processed, rows = load_processed(output_path)
    files = list_raw_files(RAW_DIR)
    new_count = 0
    next_index = len(rows) + 1
    with open(output_path, "a", encoding="utf-8") as file_handle:
        for name in files:
            if name in processed:
                continue
            path = os.path.join(RAW_DIR, name)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            row = clean_one(name, text, next_index)
            file_handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            print("已清洗：" + name + " → " + row["id"])
            next_index = next_index + 1
            new_count = new_count + 1
    print("完成：新增 " + str(new_count) + " 份")


if __name__ == "__main__":
    main()
