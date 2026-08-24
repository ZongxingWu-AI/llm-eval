#!/usr/bin/env python3
"""统一的模型客户端模块：读配置、建客户端、调用模型。

这里集中了所有脚本共用的模型相关代码：
  - load_env：读取 .env；
  - read_role / is_role_configured：读取选手、裁判的角色配置；
  - build_client：创建 openai 客户端；
  - call_model：调用一次模型，带 3 次重试和思考截断兜底。

generate_answers.py 和 judge.py 都复用它，避免各自重复写一遍调用逻辑。

项目位置：core/llm_client.py。
主要用途：公共基础层，提供多条评测线共用的配置、模型调用、Prompt、JSON 和运行元数据能力。
输入：输入来自三条评测线的调用方、环境变量或公共数据文件。
输出：输出返回给调用方，或由具体公共函数写入调用方指定的文件。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：具体函数是否调用模型、写文件或读取环境变量，以函数 docstring 和实现为准。
"""

import os    # 用来读环境变量、拼路径
import sys   # 用来打印错误、退出
import time  # 用来计时、在重试之间休眠


# 项目根目录：本文件在 llm-eval/runner/ 下，往上一级就是 llm-eval。
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 所有角色共用的默认地址。
DEFAULT_BASE_URL = "https://api.deepseek.com"


def load_env():
    """读取 .env 文件，把里面的变量装进环境变量。

    输入：无。
    输出：无（副作用：把 .env 里的变量读进 os.environ）。
    """
    try:
        from dotenv import load_dotenv

        # 运行前：环境变量里还没有 .env 里的配置。
        # 运行后：.env 里的 DEEPSEEK_*、CONTESTANT_*、JUDGE_* 等变量被读进环境。
        env_path = os.path.join(ROOT_DIR, ".env")
        load_dotenv(env_path)
    except ImportError:
        # 没装 python-dotenv 就不读 .env，用户可以用 export 手动设置环境变量。
        pass


def read_role(prefix, default_model):
    """读取某个角色的三项配置：base_url、api_key、model。

    输入：
      prefix        角色前缀，例如 "CONTESTANT_A"、"JUDGE"、"JUDGE_2"。
      default_model 当角色没配置 model 时用的默认模型名。
    输出：一个元组 (base_url, api_key, model)。

    回退规则（哪个有值用哪个）：
      base_url：<prefix>_BASE_URL → DEEPSEEK_BASE_URL → 默认地址
      api_key ：<prefix>_API_KEY  → DEEPSEEK_API_KEY  → 空（报错）
      model   ：<prefix>_MODEL    → default_model
    """
    # 运行前：prefix 是字符串，例如 "JUDGE"。
    # 运行后：base_url / api_key / model 三个变量从环境变量里读出来。
    base_url = os.getenv(prefix + "_BASE_URL", "")
    if base_url == "":
        base_url = os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL)

    api_key = os.getenv(prefix + "_API_KEY", "")
    if api_key == "":
        api_key = os.getenv("DEEPSEEK_API_KEY", "")

    model = os.getenv(prefix + "_MODEL", "")
    if model == "":
        model = default_model

    # api_key 最终仍为空，说明没配 key，没法调用，直接报错退出。
    if api_key == "":
        print("[错误] 没有找到 " + prefix + " 的 API key。", file=sys.stderr)
        print("请在 llm-eval/.env 里配置 " + prefix + "_API_KEY，或 DEEPSEEK_API_KEY。", file=sys.stderr)
        sys.exit(1)

    # 例如读取 "JUDGE" 且只配了 DEEPSEEK_API_KEY 时，返回：
    #   ("https://api.deepseek.com", "sk-xxxx", "deepseek-v4-flash")
    return base_url, api_key, model


def is_role_configured(prefix):
    """判断某个角色是否显式配置了。

    输入：prefix 角色前缀，例如 "JUDGE_2"。
    输出：True 表示该角色的 BASE_URL / API_KEY / MODEL 至少填了一个；否则 False。

    为什么需要：多裁判时，只有显式配置了才启用该裁判；
    否则空配置会悄悄回退成 DeepSeek，变成重复的裁判。
    """
    # 运行前：prefix 是字符串。
    # 运行后：依次检查三个配置项，任一非空就认为配置了。
    base_url = os.getenv(prefix + "_BASE_URL", "")
    if base_url.strip() != "":
        return True
    api_key = os.getenv(prefix + "_API_KEY", "")
    if api_key.strip() != "":
        return True
    model = os.getenv(prefix + "_MODEL", "")
    if model.strip() != "":
        return True
    return False


def build_client(base_url, api_key):
    """用给定的地址和 key 创建 openai 客户端对象。

    输入：base_url 接口地址，api_key 密钥。
    输出：openai 客户端对象，之后用它发请求。
    """
    # 运行前：base_url 和 api_key 是两个字符串，例如
    #   base_url="https://api.deepseek.com"，api_key="sk-xxxx"。
    # 运行后：client 变成 openai 客户端对象，之后所有请求都由它发出。
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)
    return client


def call_model(client, model, prompt, temperature, max_tokens):
    """调用一次模型，带 3 次重试。

    输入：
      client      是 openai 客户端；
      model       是模型名；
      prompt      是提示词；
      temperature 是采样温度；
      max_tokens  是单次最多生成的 token 数。
    输出：一个四元组 (文本, 延迟秒数, token 数, finish_reason)。

    为什么重试：网络可能抖动、限流，重试 3 次（1 秒、2 秒、4 秒）能提高成功率。
    为什么有 reasoning 兜底：思考类模型的最终答案在 content，若思考被截断，
    content 可能为空，答案残留在 reasoning_content 里。
    """
    last_err = None
    for attempt in range(3):
        try:
            # 运行前：prompt 是拼好的提示词。
            start_time = time.time()
            # 运行后：resp 是接口返回的完整响应对象。
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            message = resp.choices[0].message
            finish_reason = resp.choices[0].finish_reason
            if finish_reason is None:
                finish_reason = ""
            content = message.content
            if content is None:
                content = ""
            text = content.strip()
            # content 为空时，退回 reasoning_content（思考过程）里找答案。
            if text == "":
                if hasattr(message, "reasoning_content"):
                    reasoning = message.reasoning_content
                else:
                    reasoning = ""
                if reasoning is None:
                    reasoning = ""
                text = reasoning.strip()
            usage = resp.usage
            if usage is None:
                tokens = 0
            else:
                tokens = int(usage.total_tokens)
            latency = time.time() - start_time
            # 运行后：四个值一起返回，例如 ("C", 1.2, 180, "stop")。
            return text, latency, tokens, finish_reason
        except Exception as exc:
            last_err = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError("模型调用失败：" + str(last_err))
