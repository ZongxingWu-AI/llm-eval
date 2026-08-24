"""C-Eval 客观题评测模块。

输入是标准 C-Eval JSONL、Prompt 模板和被测模型配置，输出逐题预测 JSONL、错误记录、报告和运行元数据。
模块把模型文本抽取为 A/B/C/D 并与标准答案比较，最终汇总准确率。
运行评测会调用模型并写 C-Eval 自己的 results 目录。"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from core import llm_client

from core.data_io import read_jsonl, write_jsonl
from core.prompt_loader import load_template, render
from core.run_metadata import new_run_metadata
from tracks.ceval.paths import DATA_ROOT, PROMPT_ROOT, RESULTS_ROOT

DEFAULT_SUBJECT = "computer_network"
DEFAULT_MAX_TOKENS = 8192


def build_prompt(question: dict) -> str:
    """用途：把一道 C-Eval 题干和 A-D 选项渲染为客观题 Prompt。

    输入：question：含 question、A、B、C、D 的字典。
    输出：返回要求模型输出选项字母的 Prompt。
    副作用：读取模板，不调用模型、不写结果。
    异常或失败处理：缺字段按空字符串渲染；模板缺失时抛异常。"""

    template = load_template("ceval_prompt.md", PROMPT_ROOT)
    prompt_values: dict[str, str] = {}
    for key in ("question", "A", "B", "C", "D"):
        prompt_values[key] = question.get(key, "")
    return render(template, prompt_values)


def extract_answer(text: str) -> str:
    """用途：从模型自由文本提取 A、B、C 或 D。

    输入：text：模型原始回答。
    输出：返回规范化大写字母或空串。
    运行前数据形态：回答可能是单字母、答案：C 或解释文本。
    运行后数据变化：按明确答案表达优先的正则提取。
    副作用：只处理内存。
    异常或失败处理：空文本或找不到选项时返回空串。
    最小示例：我选择 C 会得到 C。"""

    if not text:
        return ""
    stripped = text.strip().upper()
    if stripped in {"A", "B", "C", "D"}:
        return stripped
    for pattern in (
        r"(?:答案|选项|选择)\s*(?:是|为|：|:)?\s*([ABCD])\b",
        r"\b([ABCD])\s*[\.、)）:]", r"\b([ABCD])\b", r"选\s*([ABCD])",
    ):
        match = re.search(pattern, stripped)
        if match:
            return match.group(1)
    return ""


def evaluate_rows(rows: list[dict], client, model: str, max_tokens: int = DEFAULT_MAX_TOKENS) -> list[dict]:
    """用途：逐题调用选手模型并形成 C-Eval 明细。

    输入：rows：标准题目；client/model/max_tokens：模型配置。
    输出：返回新增预测、正确性、耗时和错误字段的列表。
    运行前数据形态：每行已有标准 answer，尚无模型预测。
    运行后数据变化：复制原字段并增加 raw_response、model_answer、is_correct 等。
    副作用：会调用模型并打印进度；不直接写文件。
    异常或失败处理：单题异常写入该题 error，不中断后续题目。"""

    results: list[dict] = []
    total = len(rows)
    for index, question in enumerate(rows, start=1):
        print(f"[C-Eval] {index}/{total} {question.get('id', '')} ...", end=" ", flush=True)
        try:
            prompt = build_prompt(question)
            text, latency, tokens, finish_reason = llm_client.call_model(
                client, model, prompt, 0, max_tokens,
            )
            answer = extract_answer(text)
            correct_answer = str(question.get("answer", "")).upper()
            is_correct = answer == correct_answer
            error = "" if answer else "未提取到 A/B/C/D"
            row = {
                **question,
                "model": model,
                "raw_response": text,
                "model_answer": answer,
                "is_correct": is_correct,
                "latency_s": latency,
                "tokens": tokens,
                "finish_reason": finish_reason,
                "error": error,
            }
            print("OK" if not row["error"] else "无法提取答案")
        except Exception as exc:
            row = {**question, "model": model, "raw_response": "", "model_answer": "", "is_correct": False,
                   "latency_s": 0, "tokens": 0, "finish_reason": "", "error": str(exc)}
            print(f"ERROR: {exc}")
        results.append(row)
    return results


def run(subject: str = DEFAULT_SUBJECT, input_path: str | Path | None = None,
        output_path: str | Path | None = None, max_items: int | None = None) -> list[dict]:
    """用途：执行一次 C-Eval 学科评测并汇总准确率。

    输入：subject、可选输入/输出路径和 max_items。
    输出：返回逐题结果列表。
    运行前数据形态：输入 JSONL 一行一题。
    运行后数据变化：写逐题结果，并用无 error 题目计算 accuracy。
    副作用：读取环境变量、调用模型并覆盖结果 JSONL 与 metadata。
    异常或失败处理：题集不存在时抛 FileNotFoundError；单题错误由 evaluate_rows 记录。
    最小示例：max_items=2 只评测前两题。"""

    llm_client.load_env()
    source = Path(input_path) if input_path else DATA_ROOT / f"ceval_{subject}.jsonl"
    if not source.is_file():
        raise FileNotFoundError(f"找不到题集：{source}；请先运行 python -m tracks.ceval.fetch")
    rows = read_jsonl(source)
    if max_items is not None and max_items > 0:
        rows = rows[:max_items]
    base_url, api_key, model = llm_client.read_role("CONTESTANT_A", "deepseek-v4-flash")
    client = llm_client.build_client(base_url, api_key)
    results = evaluate_rows(rows, client, model, int(os.getenv("DEEPSEEK_MAX_TOKENS", DEFAULT_MAX_TOKENS)))
    target = Path(output_path) if output_path else RESULTS_ROOT / f"ceval_{subject}.jsonl"
    write_jsonl(target, results)
    valid: list[dict] = []
    for row in results:
        if not row["error"]:
            valid.append(row)
    correct = 0
    for row in valid:
        if row["is_correct"]:
            correct += 1
    if valid:
        accuracy = correct / len(valid)
    else:
        accuracy = 0.0
    metadata = new_run_metadata(
        "ceval.evaluate", subject=subject, model=model, input=str(source), output=str(target),
        total=len(results), valid=len(valid), correct=correct,
        accuracy=accuracy, errors=len(results) - len(valid),
    )
    target.with_suffix(target.suffix + ".metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已写入：{target}")
    print(f"正确率：{metadata['accuracy'] * 100:.2f}% ({correct}/{len(valid)})")
    return results


def main() -> None:
    """用途：解析 C-Eval 评测 CLI 参数并调用 run。

    输入：命令行 --subject、--input、--output、--max-items。
    输出：成功打印路径和准确率；失败退出 1。
    副作用：可能调用模型并覆盖结果文件。
    异常或失败处理：捕获异常后写 stderr 并 SystemExit(1)。"""

    parser = argparse.ArgumentParser(description="运行 C-Eval 单学科评测")
    parser.add_argument("--subject", default=DEFAULT_SUBJECT, help="C-Eval 学科名")
    parser.add_argument("--input", help="输入 JSONL；默认按 subject 从本评测线 data 读取")
    parser.add_argument("--output", help="输出 JSONL；默认写入本评测线 results")
    parser.add_argument("--max-items", "--max-questions", type=int, default=None, help="只跑前 N 题")
    args = parser.parse_args()
    try:
        run(args.subject, args.input, args.output, args.max_items)
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
