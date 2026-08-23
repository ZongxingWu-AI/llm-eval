#!/usr/bin/env python3
"""把 data/ 和 results/ 下的每个 .jsonl 转成同名 .xlsx，方便阅读。

用法:
    python to_excel.py

输出:
    每个 jsonl 旁边生成同名 xlsx，例如
      data/ceval_computer_network.jsonl  →  data/ceval_computer_network.xlsx
      results/judge_pairs.jsonl          →  results/judge_pairs.xlsx
"""

import json  # 用来把每一行 JSON 文本解析成字典
import os    # 用来拼接路径、列出目录里的文件

import pandas as pd  # 用来把字典列表变成表格并写入 Excel


# 脚本所在目录，后面所有路径都基于它。
HERE = os.path.dirname(os.path.abspath(__file__))
# 要转换的两个目录：题集在 data，结果在 results。
DATA_DIR = os.path.join(HERE, "data")
RESULTS_DIR = os.path.join(HERE, "results")


def jsonl_to_dataframe(path):
    """把一个 JSONL 文件读成 pandas 表格（DataFrame）。

    输入：path 是 jsonl 文件的路径。
    输出：一个 DataFrame，每一行是一道题/一条结果，每一列是一个字段。

    为什么手动逐行读：JSONL 每行是一个独立的 JSON 对象，
    手动读能保证字段顺序和原文件完全一致。
    """
    # 运行前：rows 是空列表。
    rows = []
    with open(path, encoding="utf-8") as file_handle:
        for line in file_handle:
            line = line.strip()
            if line == "":
                continue
            # 运行后：把这一行解析成字典，加进列表。
            row = json.loads(line)
            rows.append(row)
    # 运行前：rows 是字典列表，每个字典是一道题/一条结果。
    # 运行后：dataframe 变成一张表格，例如
    #   id                   question        gold  model_answer  is_correct ...
    #   computer_network-0000  使用位填充方法……  C     C            True
    dataframe = pd.DataFrame(rows)
    return dataframe


def convert_all():
    """遍历 data/ 和 results/ 下所有 jsonl，逐个转成同名 xlsx。

    输入：无。
    输出：无（副作用：在每个 jsonl 旁边生成同名 .xlsx）。
    """
    # 把两个目录合并成一个列表，先 data 后 results。
    dirs = [DATA_DIR, RESULTS_DIR]
    # count 记录一共生成几个 Excel 文件。
    count = 0
    for folder in dirs:
        # 目录不存在就跳过（例如还没生成 results 目录时）。
        if not os.path.exists(folder):
            continue
        # 拿到目录里的所有文件名。
        names = os.listdir(folder)
        for name in names:
            # 只处理 .jsonl 结尾的文件。
            if not name.endswith(".jsonl"):
                continue
            # 运行前：jsonl_path 指向 jsonl 文件。
            # 运行后：xlsx_path 指向同名 xlsx 文件，例如
            #   ".../llm-eval/data/ceval_computer_network.xlsx"。
            jsonl_path = os.path.join(folder, name)
            xlsx_path = jsonl_path[:-6] + ".xlsx"
            # 运行后：dataframe 变成这张 jsonl 的表格。
            dataframe = jsonl_to_dataframe(jsonl_path)
            # sheet 名取文件名去掉 .jsonl 后缀，例如 "ceval_computer_network"。
            sheet_name = name[:-6]
            # 运行后：把表格写进 xlsx 文件（每个文件只有一个 sheet）。
            # index=False 表示不额外加一列行号，只保留原始字段。
            dataframe.to_excel(xlsx_path, sheet_name=sheet_name, index=False)
            # 打印这一行：xlsx 路径 + 行数。
            print(xlsx_path + " | " + str(len(dataframe)) + " 行")
            count = count + 1
    # 打印生成的文件总数。
    print("共生成 " + str(count) + " 个 Excel 文件")


def main():
    """程序入口：执行转换。"""
    convert_all()


# 只有直接运行这个脚本时才执行 main()。
if __name__ == "__main__":
    main()
