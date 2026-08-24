"""C-Eval 数据获取模块。

输入是学科名称、数据集配置和输出路径，输出标准字段 id、subject、question、A-D、answer 的 JSONL。
它是 C-Eval 评测线上游，产物交给 evaluate；会访问数据集来源并写 data 目录，但不调用被测模型。"""

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
    """用途：移除 NO_PROXY/no_proxy 中不兼容的 IPv6 回环项。

    输入：无参数，读取两个代理变量。
    输出：返回 None。
    运行前数据形态：变量是逗号分隔值，可能含 ::1。
    运行后数据变化：保留其他项后写回。
    副作用：修改当前进程环境变量；不写数据、不调用模型。
    异常或失败处理：变量不存在时直接跳过。
    最小示例：localhost,::1 会变为 localhost。"""

    for variable in ("NO_PROXY", "no_proxy"):
        original = os.environ.get(variable, "")
        if not original:
            continue
        parts: list[str] = []
        for part in original.split(","):
            parts.append(part.strip())

        cleaned: list[str] = []
        for part in parts:
            if part not in {"::1", "::1/128"}:
                cleaned.append(part)
        if cleaned != parts:
            os.environ[variable] = ",".join(cleaned)


def fetch_rows(subject: str, split: str = "val", max_items: int | None = None) -> list[dict]:
    """用途：下载指定 C-Eval 学科和 split 并标准化字段。

    输入：subject、split、可选 max_items。
    输出：返回含 id、subject、question、A-D、answer 的列表。
    副作用：访问 Hugging Face 并设置 HF_ENDPOINT；不写文件。
    异常或失败处理：缺 datasets 时抛 RuntimeError，下载错误向上抛出。"""

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
    """用途：解析 C-Eval 下载 CLI 并写题目及元数据。

    输入：命令行 --subject、--split、--output、--max-items。
    输出：生成题目 JSONL 和同名 metadata.json。
    副作用：访问网络、创建目录并覆盖输出文件。
    异常或失败处理：下载失败时打印 stderr 并 SystemExit(1)。"""

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
