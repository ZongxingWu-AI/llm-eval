"""项目模块：tracks/ceval/evaluate.py。

本文件属于三条评测线或公共工具层的一部分，负责完成本文件名对应的处理步骤。输入来自上游函数或数据目录，输出返回给下游函数或写入对应结果目录。

项目位置：tracks/ceval/evaluate.py。
主要用途：C-Eval 客观题评测线，负责题目获取、模型作答和客观准确率统计。
输入：输入来自本评测线的 data 目录、公共模型客户端和 Prompt。
输出：输出写入本评测线的 results 目录，供准确率汇总和报告使用。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：fetch 可能访问数据源；evaluate 会调用模型并写评测结果。
"""

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
    """把 C-Eval 单道题的题干和选项拼成统一 Prompt。调用前是包含 question 与 A-D 的题目字典，调用后是要求模型只返回选项字母的文本。"""

    template = load_template("ceval_prompt.md", PROMPT_ROOT)
    return render(template, {key: question.get(key, "") for key in ("question", "A", "B", "C", "D")})


def extract_answer(text: str) -> str:
    """从 C-Eval 模型原始输出中提取规范化选项字母。

    输入可以是单独的 ``A``，也可以是“答案：C”或带解释的文本；输出只会是
    ``A``、``B``、``C``、``D`` 或空字符串。函数不调用模型、不写文件，空字符串
    会让上游把该题记录为“未提取到答案”。
    """

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
    """逐题调用模型并计算 C-Eval 结果。

    调用前每条题目含 ``question``、选项和标准 ``answer``；调用后复制题目并新增
    ``raw_response``、``model_answer``、``is_correct``、耗时、token、结束原因和错误字段。
    例如模型回答“答案：C”会保存原文，同时把 ``model_answer`` 设为 ``C``。
    单题调用失败只影响该题，不会中断整批评测；函数会调用模型但不直接写文件。
    """

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
    """完成当前模块中的一个处理步骤。

参数：subject、input_path、output_path、max_items。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

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
    """完成当前模块中的一个处理步骤。

参数：无。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

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
