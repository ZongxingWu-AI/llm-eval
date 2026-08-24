"""开放题候选回答生成模块。

输入是问题 JSONL 和 CONTESTANT_A、CONTESTANT_B 两组模型配置，输出含 answer_a、answer_b 和模型元数据的回答 JSONL。
产物交给 Pairwise evaluate；运行时会调用两个被测模型并写本评测线 data/results 指定位置。"""

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
    """用途：让两个选手模型分别回答开放题，并写出带原始选手身份的回答数据。

    输入：input_path、output_path 是问题和回答 JSONL；max_items 限制试跑题数。
    输出：返回含 answer_a、answer_b、model_a、model_b 和 error 的列表。
    运行前数据形态：运行前每行只有 id 和 question。
    运行后数据变化：运行后每题新增两份回答、两个模型身份和错误字段。
    副作用：读取环境变量，调用模型生成两位选手回答，并覆盖回答 JSONL 与 metadata。
    异常或失败处理：单题模型异常写入 error 后继续；输入不存在时抛出 FileNotFoundError。"""

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
    """用途：解析开放题回答生成 CLI 并调用 generate。

    输入：命令行 --input、--output、--max-items。
    输出：成功打印输出路径；失败退出 1。
    副作用：会调用两个选手模型并写文件。
    异常或失败处理：捕获异常后打印 stderr 并 SystemExit(1)。"""

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
