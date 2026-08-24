"""项目模块：tracks/ceval/fetch.py。

本文件属于三条评测线或公共工具层的一部分，负责完成本文件名对应的处理步骤。输入来自上游函数或数据目录，输出返回给下游函数或写入对应结果目录。

项目位置：tracks/ceval/fetch.py。
主要用途：C-Eval 客观题评测线，负责题目获取、模型作答和客观准确率统计。
输入：输入来自本评测线的 data 目录、公共模型客户端和 Prompt。
输出：输出写入本评测线的 results 目录，供准确率汇总和报告使用。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：fetch 可能访问数据源；evaluate 会调用模型并写评测结果。
"""

import argparse
import json
import os
import sys
from pathlib import Path

from core.data_io import write_jsonl

from core.run_metadata import new_run_metadata
from tracks.ceval.paths import DATA_ROOT

DEFAULT_SUBJECT = "computer_network"


def _sanitize_no_proxy() -> None:
    """为同一文件中的公开流程提供一个小而明确的辅助步骤。

参数：无。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    for variable in ("NO_PROXY", "no_proxy"):
        original = os.environ.get(variable, "")
        if not original:
            continue
        parts = [part.strip() for part in original.split(",")]
        cleaned = [part for part in parts if part not in {"::1", "::1/128"}]
        if cleaned != parts:
            os.environ[variable] = ",".join(cleaned)


def fetch_rows(subject: str, split: str = "val", max_items: int | None = None) -> list[dict]:
    """下载或读取指定 C-Eval 科目的题目。调用前是科目名、数据 split 和数量限制，调用后返回标准化题目字典列表。"""

    _sanitize_no_proxy()
    os.environ.setdefault("HF_ENDPOINT", "https://huggingface.co")
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("缺少 datasets 依赖，请先安装 requirements.txt") from exc
    dataset = load_dataset("ceval/ceval-exam", name=subject, split=split)
    rows: list[dict] = []
    for index, item in enumerate(dataset):
        if max_items is not None and max_items > 0 and index >= max_items:
            break
        rows.append({
            "id": f"{subject}-{index:04d}", "subject": subject,
            "question": str(item.get("question", "")),
            "A": str(item.get("A", "")), "B": str(item.get("B", "")),
            "C": str(item.get("C", "")), "D": str(item.get("D", "")),
            "answer": str(item.get("answer", "")).strip().upper(),
        })
    return rows


def main() -> None:
    """完成当前模块中的一个处理步骤。

参数：无。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    parser = argparse.ArgumentParser(description="下载 C-Eval 单个学科为 JSONL")
    parser.add_argument("--subject", default=DEFAULT_SUBJECT, help="C-Eval 学科名")
    parser.add_argument("--split", default="val", help="数据分片，默认 val")
    parser.add_argument("--output", help="输出 JSONL；默认写入本评测线 data 目录")
    parser.add_argument("--max-items", type=int, default=None, help="只下载前 N 题")
    args = parser.parse_args()
    output = Path(args.output) if args.output else DATA_ROOT / f"ceval_{args.subject}.jsonl"
    try:
        rows = fetch_rows(args.subject, args.split, args.max_items)
    except Exception as exc:
        print(f"[错误] 下载 C-Eval 失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    write_jsonl(output, rows)
    metadata = new_run_metadata("ceval.fetch", subject=args.subject, split=args.split, count=len(rows), output=str(output))
    output.with_suffix(output.suffix + ".metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成：{output}，共 {len(rows)} 题")


if __name__ == "__main__":
    main()
