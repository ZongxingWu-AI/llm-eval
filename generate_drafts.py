#!/usr/bin/env python3
"""AI 辅助出题：读清洗后的案情，调模型按草稿 schema 批量生成候选草稿。

生成的草稿会追加到 data/drafts/legal_drafts.jsonl，并带上「待审」标记。
build_legal_dataset.py 默认跳过待审草稿；人工审完把标记改成 false 或删掉后，
重新 build 才会把它纳入正式题集。

运行:
    python generate_drafts.py
    python generate_drafts.py --max-cases 1
    python generate_drafts.py --cases "case_0001,case_0002" --questions-per-case 3
"""

import argparse
import json
import os
import sys

from runner import llm_client
from prompts import loader
from judge import pairwise  # 复用它的 JSON 解析函数


# 项目根目录。
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
CLEANED_PATH = os.path.join(DATA_DIR, "cleaned", "cleaned_judgments.jsonl")
DIMENSIONS_PATH = os.path.join(DATA_DIR, "legal_dimensions.json")
DRAFTS_PATH = os.path.join(DATA_DIR, "drafts", "legal_drafts.jsonl")

# 草稿必须有的字段。
REQUIRED_FIELDS = ["维度", "类型", "问题", "标准答案要点", "评分细则", "判分方式"]


def load_cases():
    """读取清洗后的案情列表。"""
    if not os.path.exists(CLEANED_PATH):
        print("[错误] 找不到清洗结果：" + CLEANED_PATH, file=sys.stderr)
        print("请先运行：python clean_judgments.py", file=sys.stderr)
        sys.exit(1)
    rows = []
    with open(CLEANED_PATH, encoding="utf-8") as file_handle:
        for line in file_handle:
            line = line.strip()
            if line == "":
                continue
            rows.append(json.loads(line))
    return rows


def load_dimensions():
    """读取维度表，返回列表。"""
    with open(DIMENSIONS_PATH, encoding="utf-8") as file_handle:
        return json.load(file_handle)


def is_empty(value):
    """判断一个值是否为空（None、空字符串或空列表都算空）。"""
    if value is None:
        return True
    if value == "":
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    return False


def generate_one_case(client, model, case, dimensions, questions_per_case):
    """对一份案情调用模型生成草稿，返回 (草稿列表, 跳过条数)。

    输入：client/model 是起草模型；case 是清洗后的案情字典；
          dimensions 是维度表；questions_per_case 是每题条数要求。
    输出：一个元组，第一项是通过最小字段校验的草稿列表（已补 based_on_case 和待审标记），
          第二项是被跳过的条数。
    """
    dimensions_text = "、".join(dimensions)
    case_text = json.dumps(case, ensure_ascii=False)
    template = loader.load_template("legal_draft_prompt.md")
    # 运行前：template 里还有 {{案情}}、{{维度表}}、{{questions_per_case}} 占位符。
    # 运行后：prompt 变成填好内容的出题提示词。
    prompt = loader.render(
        template,
        {"案情": case_text, "维度表": dimensions_text, "questions_per_case": str(questions_per_case)},
    )
    result = llm_client.call_model(client, model, prompt, 0, 8192)
    raw = result[0]
    # 运行后：data 可能是单个对象或对象数组，统一转成列表处理。
    data = pairwise.parse_judge_json(raw)
    if data is None:
        return [], 1
    if not isinstance(data, list):
        data = [data]
    drafts = []
    skipped = 0
    for item in data:
        missing = []
        for field in REQUIRED_FIELDS:
            if is_empty(item.get(field)):
                missing.append(field)
        if len(missing) > 0:
            skipped = skipped + 1
            continue
        # 运行前：item 是模型输出的候选草稿。
        # 运行后：item 补上来源案号和待审标记，变成合法的草稿行。
        item["based_on_case"] = case.get("id", case.get("source_file", ""))
        item["待审"] = True
        drafts.append(item)
    return drafts, skipped


def main():
    """程序入口：读案情、逐案生成草稿、追加写入草稿文件。"""
    parser = argparse.ArgumentParser(description="AI 辅助出题")
    parser.add_argument("--max-cases", type=int, default=None, help="最多处理前 N 条案情")
    parser.add_argument("--cases", default="", help="只处理指定案号，逗号分隔，如 case_0001,case_0002")
    parser.add_argument("--questions-per-case", type=int, default=2, help="每条案情生成几道题，默认 2")
    args = parser.parse_args()

    llm_client.load_env()
    # 起草模型默认用 CONTESTANT_A（人工审核兜底，AI 只负责出草稿）。
    base, key, model = llm_client.read_role("CONTESTANT_A", "deepseek-v4-flash")
    client = llm_client.build_client(base, key)

    cases = load_cases()
    # 运行前：cases 是全部清洗后的案情。
    if args.cases != "":
        wanted = args.cases.split(",")
        filtered = []
        for case in cases:
            if case.get("id", "") in wanted:
                filtered.append(case)
        cases = filtered
    # 运行后：cases 变成前 N 条（传了 --max-cases 时）。
    if args.max_cases is not None and args.max_cases > 0:
        cases = cases[:args.max_cases]

    dimensions = load_dimensions()
    total_generated = 0
    with open(DRAFTS_PATH, "a", encoding="utf-8") as file_handle:
        for i, case in enumerate(cases, start=1):
            print("[起草] " + str(i) + "/" + str(len(cases)) + " " + case.get("id", "") + " ...", end=" ", flush=True)
            drafts, skipped = generate_one_case(client, model, case, dimensions, args.questions_per_case)
            for draft in drafts:
                # 运行前：draft 是内存里的草稿字典。
                # 运行后：写成一行的 JSON 追加到草稿文件。
                line = json.dumps(draft, ensure_ascii=False)
                file_handle.write(line + "\n")
            print("生成 " + str(len(drafts)) + " 条，跳过 " + str(skipped) + " 条")
            total_generated = total_generated + len(drafts)
    print("完成：新增 " + str(total_generated) + " 条待审草稿 → " + DRAFTS_PATH)


if __name__ == "__main__":
    main()
