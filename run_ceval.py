#!/usr/bin/env python3
"""用 DeepSeek 跑 C-Eval 单学科评测。

这个脚本做一件完整的事：
  读取一份 C-Eval 题集（JSONL 格式），逐题问 DeepSeek，提取选项字母，
  和标准答案比对，把每题结果写成 JSONL，最后在终端打印正确率摘要。

用法:
    python run_ceval.py                                    # 真实 API（需要 .env 里配好 DEEPSEEK_API_KEY）
    python run_ceval.py --subject computer_network         # 指定学科
    python run_ceval.py --max-questions 5                  # 只跑前 5 题

输入:
    data/ceval_<subject>.jsonl（由 fetch_ceval.py 生成）

输出:
    results/ceval_<subject>.jsonl
"""

import argparse  # 用来解析命令行参数，比如 --subject、--max-questions
import json      # 用来把字典转成 JSON 字符串、把 JSON 文本读回字典
import os        # 用来拼接文件路径、读取环境变量
import re        # 用来从模型回答里提取 A/B/C/D 字母
import sys       # 用来向 stderr 打印错误、用 sys.exit 提前退出
import time      # 用来计时、在两次请求之间休眠控速

from prompts import loader  # 加载提示词模板（在 prompts/templates 下）

# python-dotenv 用来读取 .env 文件（把 key 写进环境变量）。
# 用 try/except 包起来：即使没装这个库，脚本也能跑，只是不读 .env。
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# 脚本所在目录。
# os.path.abspath(__file__) 得到脚本的绝对路径，os.path.dirname 取它所在目录。
# 后面所有文件路径都基于这个目录，这样在哪个目录下运行脚本，结果都一样。
HERE = os.path.dirname(os.path.abspath(__file__))
# 题集目录和结果目录，都在脚本目录下面。
DATA_DIR = os.path.join(HERE, "data")
RESULTS_DIR = os.path.join(HERE, "results")

# 默认学科名：C-Eval 的计算机网络，val 集约 19 题，适合先跑通流程。
DEFAULT_SUBJECT = "computer_network"
# DeepSeek 的 API 地址（OpenAI 兼容格式，所以用 openai 的客户端来调）。
DEFAULT_BASE_URL = "https://api.deepseek.com"
# 默认模型：deepseek-v4-flash。
# 它是思考类模型，会先输出大段 reasoning_content（思考过程）再给最终答案。
DEFAULT_MODEL = "deepseek-v4-flash"
# 单次回答最多生成多少 token。
# 思考类模型的思考过程可能非常长，max_tokens 太小会被思考过程占满，
# 最终答案就没机会输出（finish_reason=length、content 为空），
# 这正是文档 07 里 K3 思考模式踩过的坑。
# 实测较难的选择题思考可能超过 4000 token，所以默认取 8192，
# 也可以用环境变量 DEEPSEEK_MAX_TOKENS 覆盖这个值。
DEFAULT_MAX_TOKENS = 8192
# 单题最多重试几次（应对网络抖动、限流）。
MAX_RETRIES = 3


def build_prompt(q):
    """把一道题拼成发给模型的提示词（Prompt）。

    输入：q 是一个字典，里面有题干 question，以及 A/B/C/D 四个选项文本。
    输出：一个多行字符串，格式固定，要求模型只输出一个字母。

    为什么这样做：文档 07 的实测经验是，明确要求"只输出一个字母"，
    可以避免模型啰嗦一堆、答案不好提取。
    """
    # 运行前：q 是一个字典（真实题集里的第一题），例如
    #   {
    #     "id": "computer_network-0000",
    #     "question": "使用位填充方法，以01111110为位首flag，数据为011011111111111111110010，求问传送时要添加几个0____",
    #     "A": "1", "B": "2", "C": "3", "D": "4",
    #     "answer": "C"
    #   }
    # 我们只取 question 和 A/B/C/D 四个字段来拼提示词。
    # 运行前：q 是当前这道题的字典。
    # 运行后：template 变成 ceval_prompt.md 的文本，里面还留着 {{...}} 占位符。
    template = loader.load_template("ceval_prompt.md")
    # 运行后：prompt 变成一个多行字符串，行与行之间是换行符 \n，例如
    #   "以下是一道选择题。\n题目：使用位填充方法……\nA. 1\nB. 2\nC. 3\nD. 4\n请直接回答选项字母（A/B/C/D），只输出一个字母，不要解释。"
    prompt = loader.render(
        template,
        {"question": q["question"], "A": q["A"], "B": q["B"], "C": q["C"], "D": q["D"]},
    )
    return prompt


def extract_answer(text):
    """从模型的回答里提取第一个独立的 A/B/C/D 字母。

    输入：模型返回的原始文本，可能是 "B"、"答案是 B"、"B) 正确"、"选C" 等。
    输出：选项字母字符串；找不到就返回空字符串。

    为什么这样做：模型不一定严格只输出一个字母，可能带解释，
    所以需要从文本里找出最像选项字母的那个。
    """
    # 运行前：text 是模型回答的原始文本，例如 "答案是 B" 或 "B"。
    # 运行后：返回第一个独立的选项字母，例如 "B"；找不到就返回空字符串 ""。
    # 空文本直接返回空字符串，避免后面正则白跑。
    if text == "":
        return ""
    # 运行前：text 可能是 "答案是 B" 这种带解释的文本。
    # 运行后：upper_text 变成全大写文本，例如 "答案是 B"（字母部分变成大写）。
    # 把文本全部转成大写，这样 A/a、B/b 都能匹配上。
    upper_text = text.upper()
    # 正则表达式的意思：
    #   (?<![A-Za-z]) 前面不能是字母；
    #   [ABCD]        匹配 A、B、C、D 其中一个；
    #   (?![A-Za-z])  后面不能是字母。
    # 这样能匹配独立的 B，但不会把 "AB" 或 "ANSWER" 里的字母误判成选项。
    match = re.search(r"(?<![A-Za-z])[ABCD](?![A-Za-z])", upper_text)
    # 没找到就返回空字符串，由上层按"无答案"处理。
    if match is None:
        return ""
    # 运行前：match 是正则匹配结果对象。
    # 运行后：返回 match 里匹配到的字母，例如 "B"。
    # 找到就返回那个字母。
    return match.group(0)


def call_model(client, prompt, model, max_tokens):
    """调用一次模型，带 3 次重试。

    输入：
      client     是 openai 的客户端对象（已配置好 DeepSeek 的地址和 key）；
      prompt     是拼好的提示词；
      model      是模型名；
      max_tokens 是单次最多生成的 token 数。

    输出：一个包含四个值的元组：
      (最终文本, 延迟秒数, token 数, finish_reason)
      - 最终文本：模型的回答内容；如果 content 为空，退回去读 reasoning_content。
      - 延迟秒数：这次请求花了多长时间。
      - token 数：这次请求一共消耗多少 token（包含提示词部分）。
      - finish_reason：stop 表示正常结束，length 表示生成被截断。

    为什么重试：网络请求可能超时或被限流，直接失败会让整题报废，
    重试 3 次（间隔 1 秒、2 秒、4 秒）能明显提高成功率。
    """
    # 运行前：
    #   client     是已配置好的 openai 客户端（里面藏着 DeepSeek 的地址和 key）；
    #   prompt     是上面拼好的多行提示词字符串；
    #   model      是模型名，例如 "deepseek-v4-flash"；
    #   max_tokens 是本次最多生成的 token 数，例如 8192。
    # 运行后：返回一个元组 (text, latency, tokens, finish_reason)，示意
    #   ("C", 1.2, 180, "stop")
    # last_err 用来记录最后一次异常，三次都失败后把它抛出去。
    last_err = None
    # 最多尝试 MAX_RETRIES 次（这里是 3 次）。
    for attempt in range(MAX_RETRIES):
        try:
            # 记录调用前的时刻，用来计算这次请求的延迟。
            start_time = time.time()
            # 调用 DeepSeek 接口，把提示词发给模型。
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": prompt},
                ],
                temperature=0,          # 贪婪解码：让同一题多次运行结果尽量一致
                max_tokens=max_tokens,  # 给思考过程留足空间，避免被截断
            )
            # 取第一个回答（choices 是列表，我们只需要第一个）。
            message = resp.choices[0].message
            # finish_reason：stop=正常结束，length=生成到上限被截断。
            finish_reason = resp.choices[0].finish_reason
            # 接口没返回 finish_reason 时，统一当成空字符串。
            if finish_reason is None:
                finish_reason = ""

            # 思考类模型的最终答案在 content 字段里。
            content = message.content
            # content 可能为空（思考还没结束就被截断）。
            if content is None:
                content = ""
            # 运行前：content 是模型返回的文本（可能是空字符串）。
            # 运行后：text 变成去掉首尾空白的文本，例如 "C"。
            text = content.strip()

            # 运行前：text 可能是空字符串（思考太长被截断，答案没来得及输出）。
            # 运行后：text 变成 reasoning_content 思考文本，例如
            #   "我们只需要输出字母。答案是B。"
            # 如果 content 是空的，就退回 reasoning_content（思考过程）里找答案。
            # 这是兜底：至少不会出现"无答案"，能从思考过程里碰运气提取字母。
            if text == "":
                # reasoning_content 是 DeepSeek 思考类模型特有的字段，
                # 普通模型没有这个字段，所以先判断有没有。
                if hasattr(message, "reasoning_content"):
                    reasoning = message.reasoning_content
                else:
                    reasoning = ""
                # reasoning 也可能是 None，统一成空字符串。
                if reasoning is None:
                    reasoning = ""
                text = reasoning.strip()

            # usage 记录这次请求消耗了多少 token。
            usage = resp.usage
            # 接口没返回 usage 时，token 数记 0。
            if usage is None:
                tokens = 0
            else:
                tokens = int(usage.total_tokens)

            # 用结束时刻减去开始时刻，算出延迟秒数。
            latency = time.time() - start_time
            # 运行前：text/latency/tokens/finish_reason 四个变量各自算好了。
            # 运行后：打包成一个元组返回给调用方，例如 ("C", 1.2, 180, "stop")。
            # 这次调用成功，把四个值一起返回。
            return text, latency, tokens, finish_reason
        except Exception as exc:
            # 把这次的异常记下来，下面决定是重试还是放弃。
            last_err = exc
            # 如果不是最后一次尝试，就等 1、2、4 秒再试（指数退避）。
            if attempt < MAX_RETRIES - 1:
                wait_seconds = 2 ** attempt
                time.sleep(wait_seconds)
    # 三次都失败，抛出异常，由上层把这一题标记为 error。
    raise RuntimeError("模型调用失败：" + str(last_err))


def load_questions(subject):
    """读取题集文件，返回题目字典列表。

    输入：subject 学科名，例如 "computer_network"。
    输出：一个列表，每个元素是一道题的字典（含题干、选项、标准答案）。

    为什么单独拆一个函数：读文件加解析 JSON 的逻辑独立出来，
    run() 里只关心"拿到题目列表"这一个结果，主流程更清楚。
    """
    # 运行前：subject 是学科名，例如 "computer_network"。
    # 运行后：path 变成题集文件路径，例如
    #   ".../llm-eval/data/ceval_computer_network.jsonl"
    # 拼出题集文件路径：data/ceval_<subject>.jsonl。
    path = os.path.join(DATA_DIR, "ceval_" + subject + ".jsonl")
    # 文件不存在时给出明确提示，而不是报一堆看不懂的异常。
    if not os.path.exists(path):
        print(f"[错误] 找不到题集文件：{path}", file=sys.stderr)
        print(f"请先运行：python fetch_ceval.py --subject {subject}", file=sys.stderr)
        sys.exit(1)

    # 运行前：rows 是空列表 []，下面逐行往里添加题目。
    # rows 用来装所有题目。
    rows = []
    # 打开文件逐行读取。每行是一个独立的 JSON 对象（JSONL 格式）。
    with open(path, encoding="utf-8") as file_handle:
        for line in file_handle:
            # 去掉行首行尾的空白和换行符。
            line = line.strip()
            # 跳过空行（比如文件末尾可能有一个空行）。
            if line == "":
                continue
            # 运行前：line 是去掉空白后的一行 JSON 文本。
            # 运行后：question 变成解析好的字典，例如
            #   {"id": "computer_network-0000", "question": "……", "A": "1", "B": "2", "C": "3", "D": "4", "answer": "C"}
            # 把这一行 JSON 文本解析成字典，加进题目列表。
            question = json.loads(line)
            rows.append(question)
    # 运行后：rows 变成题目字典列表（共 19 条），第一条例如
    #   {"id": "computer_network-0000", "subject": "computer_network",
    #    "question": "使用位填充方法……", "A": "1", "B": "2", "C": "3", "D": "4", "answer": "C"}
    # 返回题目列表。
    return rows


def run(subject, max_questions):
    """评测主流程。

    输入：
      subject       学科名；
      max_questions 最多跑多少题，None 表示全部跑。
    输出：无（结果写到 results/ 目录，并在终端打印摘要）。

    整个流程分 6 步：
      第 1 步：读取配置（.env）并创建客户端；
      第 2 步：读取题集；
      第 3 步：逐题调用模型、提取答案、判分；
      第 4 步：把每题结果写入结果文件；
      第 5 步：汇总统计；
      第 6 步：打印摘要。
    """
    # ---------- 第 1 步：读取配置并创建客户端 ----------
    # 如果装了 python-dotenv，就读 .env 文件，把里面的 DEEPSEEK_* 变量装进环境。
    if load_dotenv is not None:
        env_path = os.path.join(HERE, ".env")
        load_dotenv(env_path)

    # 运行前：.env 文件里写着 DEEPSEEK_API_KEY=sk-xxxx（这里用占位符，不写真 key）。
    # 运行后：api_key 变成环境变量读到的字符串，例如 "sk-xxxx"。
    # 从环境变量里取 API key；没有 key 就没法调模型，直接退出。
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    api_key = api_key.strip()
    if api_key == "":
        print("[错误] 未找到 DEEPSEEK_API_KEY。请在 llm-eval/.env 中配置（参照 .env.example），或先运行：export DEEPSEEK_API_KEY=sk-xxx", file=sys.stderr)
        sys.exit(1)

    # openai 的 SDK 支持自定义 base_url，所以用它来访问 DeepSeek。
    from openai import OpenAI

    # 运行前：api_key 和 base_url 是两个字符串。
    # 运行后：client 变成 openai 客户端对象，之后所有请求都由它发出。
    # 创建客户端：key 和地址都来自环境变量（可被 .env 覆盖）。
    base_url = os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL)
    client = OpenAI(api_key=api_key, base_url=base_url)

    # 模型名和 max_tokens 同样允许环境变量覆盖。
    model = os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL)
    # 运行前：max_tokens 还没有值。
    # 运行后：max_tokens 默认是 8192；如果配置了 DEEPSEEK_MAX_TOKENS，就用配置值（例如 4096）。
    max_tokens = DEFAULT_MAX_TOKENS
    # 如果环境变量里写了 DEEPSEEK_MAX_TOKENS，就转成整数使用。
    env_max_tokens = os.getenv("DEEPSEEK_MAX_TOKENS", "")
    if env_max_tokens != "":
        try:
            max_tokens = int(env_max_tokens)
        except ValueError:
            # 写错格式时保持默认值，不退出。
            max_tokens = DEFAULT_MAX_TOKENS

    # ---------- 第 2 步：读取题集 ----------
    # 运行前：subject 是学科名，例如 "computer_network"。
    # 运行后：questions 变成题目字典列表（共 19 条），第一条例如
    #   {"id": "computer_network-0000", "question": "使用位填充方法……", "A": "1", "B": "2", "C": "3", "D": "4", "answer": "C"}
    questions = load_questions(subject)
    # 运行前：questions 是全部 19 条题目。
    # 运行后：questions 变成前 N 条（例如 --max-questions 3 时只剩 3 条）。
    # 如果指定了只跑前 N 题，就截取列表的前 N 个。
    if max_questions is not None and max_questions > 0:
        questions = questions[:max_questions]

    # 确保结果目录存在（不存在就创建）。
    if not os.path.exists(RESULTS_DIR):
        os.makedirs(RESULTS_DIR)
    # 结果文件路径：results/ceval_<subject>.jsonl。
    out_path = os.path.join(RESULTS_DIR, "ceval_" + subject + ".jsonl")

    # ---------- 第 3 步：逐题调用模型、提取答案、判分 ----------
    # results 用来收集每一题的结果字典。
    results = []
    total = len(questions)
    # enumerate 会同时给出序号 i（从 1 开始）和题目 q。
    for i, q in enumerate(questions, start=1):
        # 运行前：q 是当前这一题的字典。
        # 运行后：prompt 变成拼好的多行提示词，例如
        #   "以下是一道选择题。\n题目：使用位填充方法……\nA. 1\nB. 2\nC. 3\nD. 4\n请直接回答选项字母……"
        # 拼这道题的提示词。
        prompt = build_prompt(q)
        # 打印进度，方便观察脚本是否卡住。
        # end=" " 表示打印后不换行，等这题的结果出来再换行。
        print(f"[{i}/{total}] {q['id']} ...", end=" ", flush=True)
        try:
            # 两次请求之间停 0.5 秒，控速避免触发限流。
            time.sleep(0.5)
            # 运行前：client/prompt/model/max_tokens 四个参数就绪。
            # 运行后：raw_text 是模型回答，例如 "C"；
            #         latency 是耗时秒数，例如 1.2；
            #         tokens 是消耗的 token 数，例如 180；
            #         finish_reason 是结束原因，例如 "stop"。
            # 调用模型，拿到回答文本、延迟、token 数、结束原因。
            raw_text, latency, tokens, finish_reason = call_model(
                client, prompt, model, max_tokens
            )
            # 运行前：raw_text 是模型回答，例如 "答案是 C"。
            # 运行后：model_answer 变成提取出的字母，例如 "C"；提取不到就是 ""。
            # 从回答里提取选项字母。
            model_answer = extract_answer(raw_text)
            # 运行前：q["answer"] 是标准答案字母，例如 "c" 或 "C"。
            # 运行后：gold 变成大写字母，例如 "C"。
            # 标准答案转成大写（题集里本来就是大写，这里保险起见）。
            gold = q["answer"].strip().upper()

            # 运行前：model_answer 和 gold 是两个字母（或空字符串）。
            # 运行后：is_correct 变成 True（两者一致且非空）或 False（不一致/无答案）。
            # 判断是否答对：答案非空，并且和标准答案一致。
            is_correct = False
            if model_answer != "" and model_answer == gold:
                is_correct = True

            # 运行前：上面算好的各变量还散落着。
            # 运行后：row 变成一个结果字典，例如
            #   {"id": "computer_network-0000", "question": "使用位填充方法……", "gold": "C",
            #    "model_answer": "C", "is_correct": True, "raw_text": "C",
            #    "finish_reason": "stop", "latency_s": 1.2, "tokens": 180, "error": ""}
            # 组装这一题的结果字典，之后写进结果文件。
            row = {
                "id": q["id"],                   # 题号
                "question": q["question"],       # 题干
                "gold": gold,                    # 标准答案
                "model_answer": model_answer,    # 模型答案（提取后）
                "is_correct": is_correct,        # 是否答对
                "raw_text": raw_text,            # 模型原始输出，留档可追溯
                "finish_reason": finish_reason,  # stop=正常结束 / length=思考被截断
                "latency_s": round(latency, 3),  # 单题耗时（秒，保留 3 位小数）
                "tokens": tokens,                # 单题 token 消耗
                "error": "",                     # 为空表示成功
            }

            # 决定终端上显示什么标记：✓ 答对、✗ 答错、无答案。
            mark = "✗"
            if is_correct:
                mark = "✓"
            elif model_answer == "":
                mark = "无答案"
            # 模型答案为空时显示 "-"，避免打印出空字符串。
            display_answer = model_answer
            if display_answer == "":
                display_answer = "-"
            print(f"{mark} (gold={gold}, model={display_answer})")
        except Exception as exc:
            # API 最终失败：这一题标记为 error，不计入正确率。
            row = {
                "id": q["id"],
                "question": q["question"],
                "gold": q["answer"].strip().upper(),
                "model_answer": "",
                "is_correct": False,
                "raw_text": "",
                "finish_reason": "",
                "latency_s": 0.0,
                "tokens": 0,
                "error": str(exc),
            }
            print("ERROR: " + str(exc))
        # 运行前：results 里还没有这一题的结果。
        # 运行后：results 末尾多了一题的结果字典（成功或失败都会加）。
        # 无论成功还是失败，都把这一题的结果收进列表。
        results.append(row)

    # ---------- 第 4 步：把结果写入文件 ----------
    # 逐行写入：每行是一个题目的 JSON 字符串。
    # ensure_ascii=False 表示中文原样保存，不转成 \uXXXX。
    with open(out_path, "w", encoding="utf-8") as file_handle:
        for row in results:
            # 运行前：row 是内存里的字典。
            # 运行后：line 变成一行 JSON 字符串，例如
            #   {"id": "computer_network-0000", "question": "……", "model_answer": "C", ...}
            line = json.dumps(row, ensure_ascii=False)
            file_handle.write(line + "\n")

    # ---------- 第 5 步：汇总统计 ----------
    # 运行前：results 里有 19 个结果字典，可能混着 error 非空的失败行。
    # 运行后：answered 变成只含成功行的列表（error 为空）。
    # answered 只包含成功调用（error 为空）的题目。
    answered = []
    for row in results:
        if row["error"] == "":
            answered.append(row)
    # 运行前：answered 是成功行的列表。
    # 运行后：correct 变成答对题数，例如 18。
    # 数一数答对了几题。
    correct = 0
    for row in answered:
        if row["is_correct"]:
            correct = correct + 1
    # 运行前：total_latency=0.0、total_tokens=0。
    # 运行后：total_latency 变成所有题耗时之和，例如 94.3；
    #         total_tokens 变成所有题 token 之和，例如 11944。
    # 统计所有有效题的总延迟和总 token。
    total_latency = 0.0
    total_tokens = 0
    for row in answered:
        total_latency = total_latency + row["latency_s"]
        total_tokens = total_tokens + row["tokens"]
    # 运行前：total 是总题数，len(answered) 是成功题数。
    # 运行后：errors 变成失败题数，例如 0。
    # 有多少题调用失败（error 非空）。
    errors = total - len(answered)
    # 运行前：correct 和 len(answered) 是两个数字。
    # 运行后：accuracy 变成正确率百分数，例如 94.74（没有有效题时保持 0.0）。
    # 计算正确率；没有有效题时避免除零。
    accuracy = 0.0
    if len(answered) > 0:
        accuracy = correct / len(answered) * 100

    # ---------- 第 6 步：打印摘要 ----------
    # 运行前：统计变量都已算好。
    # 运行后：终端打印出摘要，例如
    #   学科: computer_network | 题量: 19 | 有效: 19 | 错误: 0
    #   正确率: 94.74% (18/19)
    print("")
    print("===== 摘要 =====")
    print(f"学科: {subject} | 题量: {total} | 有效: {len(answered)} | 错误: {errors}")
    print(f"正确率: {accuracy:.2f}% ({correct}/{len(answered)})")
    print(f"总延迟: {total_latency:.1f}s | 总 token: {total_tokens}")
    if errors > 0:
        print(f"注意：{errors} 题因 API 错误未计入正确率，见结果文件的 error 字段。")
    print(f"结果已写入: {out_path}")
    # 顺手把 jsonl 同步成 Excel，方便阅读；失败只提示，不影响评测结果。
    try:
        import to_excel
        to_excel.convert_all()
    except Exception as exc:
        print("[提示] 刷新 Excel 失败（不影响评测结果）：" + str(exc), file=sys.stderr)


def main():
    """程序入口：解析命令行参数，然后执行 run()。"""
    # 创建参数解析器，加一句描述，运行 --help 时能看到。
    parser = argparse.ArgumentParser(description="用 DeepSeek 跑 C-Eval 单学科评测")
    # --subject 参数：学科名，不传时用默认值。
    parser.add_argument("--subject", default=DEFAULT_SUBJECT, help="学科名，默认 " + DEFAULT_SUBJECT)
    # --max-questions 参数：只跑前 N 题，不传表示全跑。
    parser.add_argument("--max-questions", type=int, default=None, help="只跑前 N 题")
    # 运行前：命令行参数还是字符串（例如 ["--subject", "computer_network"]）。
    # 运行后：args 变成解析结果对象，例如 args.subject="computer_network"、args.max_questions=None。
    # 解析命令行参数，得到 args 对象。
    args = parser.parse_args()
    # 运行前：args 里存着用户传入的参数。
    # 运行后：把 subject 和 max_questions 交给 run()，开始评测。
    # 把参数交给主流程执行。
    run(args.subject, args.max_questions)


# 只有直接运行这个脚本时才执行 main()。
# 如果被别的文件 import，不会执行，方便将来复用里面的函数。
if __name__ == "__main__":
    main()
