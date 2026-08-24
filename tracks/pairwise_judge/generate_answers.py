"""项目模块：tracks/pairwise_judge/generate_answers.py。

本文件属于三条评测线或公共工具层的一部分，负责完成本文件名对应的处理步骤。输入来自上游函数或数据目录，输出返回给下游函数或写入对应结果目录。

项目位置：tracks/pairwise_judge/generate_answers.py。
主要用途：开放题 LLM-as-Judge 评测线，负责生成回答、位置交换裁判、多裁判统计和报告。
输入：输入来自本评测线的 data 目录、裁判 Prompt 和公共模型客户端。
输出：输出写入本评测线的 results 目录，供偏见分析和报告阅读。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：生成和裁判模块会调用模型；统计和报告模块只处理内存数据或写结果文件。
"""

import argparse
import json
import sys
from pathlib import Path

from core import llm_client
from core.data_io import read_jsonl, write_jsonl

from core.run_metadata import new_run_metadata
from tracks.pairwise_judge.paths import DATA_ROOT


def generate(input_path: str | Path | None = None, output_path: str | Path | None = None,
             max_items: int | None = None) -> list[dict]:
    """完成当前模块中的一个处理步骤。

参数：input_path、output_path、max_items。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    source = Path(input_path) if input_path else DATA_ROOT / "judge_questions.jsonl"
    target = Path(output_path) if output_path else DATA_ROOT / "judge_answers.jsonl"
    if not source.is_file():
        raise FileNotFoundError(f"找不到开放题：{source}")
    questions = read_jsonl(source)
    if max_items is not None and max_items > 0:
        questions = questions[:max_items]
    llm_client.load_env()
    base_a, key_a, model_a = llm_client.read_role("CONTESTANT_A", "deepseek-v4-flash")
    base_b, key_b, model_b = llm_client.read_role("CONTESTANT_B", "deepseek-v4-pro")
    client_a, client_b = llm_client.build_client(base_a, key_a), llm_client.build_client(base_b, key_b)
    rows: list[dict] = []
    for index, question in enumerate(questions, start=1):
        print(f"[选手] {index}/{len(questions)} {question.get('id', '')} ...", end=" ", flush=True)
        try:
            answer_a = llm_client.call_model(client_a, model_a, question["question"], 0.2, 8192)[0]
            answer_b = llm_client.call_model(client_b, model_b, question["question"], 0.2, 8192)[0]
            row = {"id": question["id"], "question": question["question"], "answer_a": answer_a,
                   "model_a": model_a, "answer_b": answer_b, "model_b": model_b, "error": ""}
            print("OK")
        except Exception as exc:
            row = {"id": question.get("id", ""), "question": question.get("question", ""), "answer_a": "",
                   "model_a": model_a, "answer_b": "", "model_b": model_b, "error": str(exc)}
            print(f"ERROR: {exc}")
        rows.append(row)
    write_jsonl(target, rows)
    metadata = new_run_metadata("pairwise_judge.generate_answers", input=str(source), output=str(target),
                                count=len(rows), model_a=model_a, model_b=model_b)
    target.with_suffix(target.suffix + ".metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成：{target}，共 {len(rows)} 题")
    return rows


def main() -> None:
    """完成当前模块中的一个处理步骤。

参数：无。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    parser = argparse.ArgumentParser(description="用两个选手模型生成开放题回答")
    parser.add_argument("--input", help="开放题 JSONL")
    parser.add_argument("--output", help="回答输出 JSONL")
    parser.add_argument("--max-items", "--max-questions", type=int, default=None, help="只跑前 N 题")
    args = parser.parse_args()
    try:
        generate(args.input, args.output, args.max_items)
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
