#!/usr/bin/env python3
"""下载 C-Eval 单个学科（val 集）为 JSONL，供 run_ceval.py 使用。

用法:
    python fetch_ceval.py
    python fetch_ceval.py --subject advanced_mathematics

输出:
    data/ceval_<subject>.jsonl
"""

import argparse  # 用来解析命令行参数，比如 --subject
import json      # 用来把字典转成 JSON 字符串
import os        # 用来拼接路径、设置环境变量
import sys       # 用来向 stderr 打印错误、用 sys.exit 退出

# 脚本所在目录，后面所有路径都基于它。
HERE = os.path.dirname(os.path.abspath(__file__))
# 题集保存目录。
DATA_DIR = os.path.join(HERE, "data")

# 默认学科：计算机网络（val 集约 19 题，适合先跑通流程）。
DEFAULT_SUBJECT = "computer_network"


def _sanitize_no_proxy():
    """清理环境变量 no_proxy 里的 IPv6 条目。

    为什么需要：datasets / huggingface_hub 解析 no_proxy 时，
    会把 "::1" 误当成端口，报 "Invalid port: ':1'"。
    这里只改本脚本进程内的环境变量，不影响用户自己的 shell 配置。
    """
    # NO_PROXY 和 no_proxy 是同一个东西的两种写法，都要处理。
    for var in ("NO_PROXY", "no_proxy"):
        # 读取环境变量；没设置就跳过这个变量。
        val = os.environ.get(var, "")
        if val == "":
            continue
        # 运行前：val 是完整的 no_proxy 字符串，例如 "127.0.0.1,localhost,::1"。
        # 运行后：parts 变成按逗号拆开的列表，例如 ["127.0.0.1", "localhost", "::1"]。
        # 用逗号把内容拆成一段一段，例如 "127.0.0.1,localhost,::1"。
        parts = val.split(",")
        # cleaned 存放清理后剩下的段。
        cleaned = []
        for part in parts:
            # 去掉每段首尾空白。
            part = part.strip()
            # 把 IPv6 的 ::1 和 ::1/128 这两段丢掉。
            if part == "::1" or part == "::1/128":
                continue
            # 其余段保留下来。
            cleaned.append(part)
        # 运行前：cleaned 是过滤后的段列表，例如 ["127.0.0.1", "localhost"]。
        # 运行后：new_val 变成用逗号重新拼好的字符串，例如 "127.0.0.1,localhost"。
        # 如果确实删掉了东西，把清理后的值写回环境变量。
        if len(cleaned) != len(parts):
            new_val = ",".join(cleaned)
            os.environ[var] = new_val
            print(f"[提示] 已从 {var} 移除 IPv6 条目，避免 datasets 代理解析报错。", file=sys.stderr)


def fetch_rows(subject):
    """从 HuggingFace 下载一个 C-Eval 学科，返回题目字典列表。

    输入：subject 学科名，例如 "computer_network"。
    输出：一个列表，每个元素是一道题的字典。

    题目字典的字段：
      id       题号
      subject  学科名
      question 题干
      A/B/C/D  四个选项文本
      answer   标准答案字母
    """
    # 先清理 no_proxy，避免 datasets 解析代理时报错。
    _sanitize_no_proxy()

    # 默认走 HuggingFace 官方端点（通常经本机代理可达）。
    # 如果网络无法直连 huggingface.co，可显式设置 HF_ENDPOINT=https://hf-mirror.com。
    # setdefault 表示"只有没设置过时才写入"，不覆盖用户已有的配置。
    os.environ.setdefault("HF_ENDPOINT", "https://huggingface.co")

    # 延迟导入 datasets：只有真的取数时才 import，
    # 这样即使没装 datasets，脚本的其他部分（比如提示信息）也能正常走。
    from datasets import load_dataset

    # 运行前：subject 是学科名，例如 "computer_network"。
    # 运行后：dataset 变成 datasets 对象，装着该学科 val 分片的 19 条数据；
    #         遍历时每个 item 是一个字典，例如
    #   {"question": "使用位填充方法……", "A": "1", "B": "2", "C": "3", "D": "4", "answer": "C"}
    # 调用 datasets 加载 ceval/ceval-exam 数据集里指定学科、val 分片。
    try:
        dataset = load_dataset("ceval/ceval-exam", name=subject, split="val")
    except Exception as exc:
        # 加载失败时打印友好的排查提示，而不是直接抛一堆异常栈。
        print(f"[错误] 加载 C-Eval 学科 '{subject}' 失败：{exc}", file=sys.stderr)
        print("可能原因与处理：", file=sys.stderr)
        print("  1) 学科名不对：可从 cevalbenchmark.com 或 C-Eval GitHub 仓库确认学科名。", file=sys.stderr)
        print("  2) 网络不通：脚本默认 HF_ENDPOINT=https://huggingface.co，仍失败请检查网络/代理。", file=sys.stderr)
        # 尝试列出数据集可用的配置，帮助用户确认学科名。
        try:
            from datasets import get_dataset_config_names

            configs = get_dataset_config_names("ceval/ceval-exam")
            print(f"  3) 数据集可用配置（部分版本仅返回 default）：{configs}", file=sys.stderr)
        except Exception:
            # 列配置也失败就忽略，不影响主报错信息。
            pass
        sys.exit(1)

    # 运行前：rows 是空列表 []，下面在循环里逐题添加。
    # rows 存放转换好的题目字典。
    rows = []
    # enumerate 会同时给出序号 idx（从 0 开始）和数据集里的一行 item。
    for idx, item in enumerate(dataset):
        # 运行前：item 是数据集里的一行字典。
        # 运行后：row 变成统一结构的题目字典，例如
        #   {"id": "computer_network-0000", "subject": "computer_network",
        #    "question": "使用位填充方法……", "A": "1", "B": "2", "C": "3", "D": "4", "answer": "C"}
        # 把数据集里的一行转成统一的字典结构。
        row = {
            # 用学科名加序号拼题号；:04d 表示补成 4 位数字，如 computer_network-0003。
            "id": f"{subject}-{idx:04d}",
            "subject": subject,
            # item.get("question", "") 表示：取这个字段，取不到就返回空字符串。
            "question": str(item.get("question", "")),
            "A": str(item.get("A", "")),
            "B": str(item.get("B", "")),
            "C": str(item.get("C", "")),
            "D": str(item.get("D", "")),
            # 标准答案去掉空白并转成大写，方便后面比对。
            "answer": str(item.get("answer", "")).strip().upper(),
        }
        rows.append(row)
    # 运行后：rows 变成题目字典列表（共 19 条），第一条例如
    #   {"id": "computer_network-0000", "subject": "computer_network",
    #    "question": "使用位填充方法……", "A": "1", "B": "2", "C": "3", "D": "4", "answer": "C"}
    # 返回题目列表。
    return rows


def main():
    """程序入口：解析参数，下载题集并写入 JSONL 文件。"""
    # 创建参数解析器，加一句描述，运行 --help 时能看到。
    parser = argparse.ArgumentParser(description="下载 C-Eval 单个学科 val 集为 JSONL")
    # --subject 参数：学科名，不传时用默认值。
    parser.add_argument("--subject", default=DEFAULT_SUBJECT, help="学科名，默认 " + DEFAULT_SUBJECT)
    # 解析命令行参数。
    args = parser.parse_args()

    # 确保 data 目录存在（不存在就创建）。
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    # 运行前：args.subject 是学科名，例如 "computer_network"。
    # 运行后：rows 变成题目字典列表（共 19 条）。
    # 下载题集，得到题目列表。
    rows = fetch_rows(args.subject)
    # 拼输出文件路径：data/ceval_<subject>.jsonl。
    out_path = os.path.join(DATA_DIR, "ceval_" + args.subject + ".jsonl")
    # 逐行写入 JSON：每行是一道题。
    with open(out_path, "w", encoding="utf-8") as file_handle:
        for row in rows:
            # 运行前：row 是内存里的字典。
            # 运行后：line 变成一行 JSON 字符串，例如
            #   {"id": "computer_network-0000", "question": "使用位填充方法……", ...}
            line = json.dumps(row, ensure_ascii=False)
            file_handle.write(line + "\n")
    # 打印完成信息。
    print(f"完成：{out_path}，共 {len(rows)} 题")
    # 顺手把 jsonl 同步成 Excel，方便阅读；失败只提示，不影响题集生成。
    try:
        import to_excel
        to_excel.convert_all()
    except Exception as exc:
        print("[提示] 刷新 Excel 失败（不影响题集生成）：" + str(exc), file=sys.stderr)


# 只有直接运行这个脚本时才执行 main()。
if __name__ == "__main__":
    main()
