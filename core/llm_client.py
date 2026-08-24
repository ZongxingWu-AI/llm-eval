#!/usr/bin/env python3
"""公共大模型客户端模块。

输入来自 .env、角色环境变量和调用方提供的 Prompt；输出模型文本、延迟、token 数与结束原因。
三条评测线通过本模块统一创建 OpenAI 兼容客户端、读取角色配置和执行重试。
本模块会读取环境变量并在 call_model 中发起网络模型请求，但不写评测结果文件。"""

import os    # 用来读环境变量、拼路径
import sys   # 用来打印错误、退出
import time  # 用来计时、在重试之间休眠


# 项目根目录：本文件在 llm-eval/runner/ 下，往上一级就是 llm-eval。
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 所有角色共用的默认地址。
DEFAULT_BASE_URL = "https://api.deepseek.com"


def load_env():
    """用途：把项目根目录 .env 配置加载到进程环境变量。

    输入：无显式参数。
    输出：返回 None。
    副作用：读取 .env 并修改 os.environ；不调用模型。
    异常或失败处理：未安装 python-dotenv 时静默跳过。"""
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
    """用途：读取选手或裁判角色的接口地址、密钥和模型名。

    输入：prefix：角色前缀；default_model：默认模型。
    输出：返回 (base_url, api_key, model)。
    运行前数据形态：配置可能分散在角色变量和 DEEPSEEK 通用变量。
    运行后数据变化：按角色专用、通用和默认值顺序回退。
    副作用：读取环境变量，不调用模型、不写文件。
    异常或失败处理：最终没有 API key 时打印错误并 SystemExit(1)。"""
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
    """用途：判断可选角色是否显式配置。

    输入：prefix：例如 JUDGE_2。
    输出：任一角色专用变量非空时返回 True。
    副作用：只读取环境变量。
    异常或失败处理：空白值视为未配置。"""
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
    """用途：创建 OpenAI 兼容 API 客户端。

    输入：base_url：接口地址；api_key：密钥。
    输出：返回 OpenAI 客户端对象。
    副作用：创建客户端但不发起模型请求。
    异常或失败处理：缺少 openai 依赖时抛出 RuntimeError。"""
    # 运行前：base_url 和 api_key 是两个字符串，例如
    #   base_url="https://api.deepseek.com"，api_key="sk-xxxx"。
    # 运行后：client 变成 openai 客户端对象，之后所有请求都由它发出。
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)
    return client


def call_model(client, model, prompt, temperature, max_tokens):
    """用途：调用聊天模型并在临时错误时最多重试三次。

    输入：client、model、prompt、temperature、max_tokens。
    输出：返回 (文本, 延迟秒数, token 总数, finish_reason)。
    运行前数据形态：输入是完整 Prompt 和已创建客户端。
    运行后数据变化：响应被规范化为四元组，content 为空时回退 reasoning_content。
    副作用：会调用模型并在重试间休眠；不写文件。
    异常或失败处理：三次失败后抛出 RuntimeError，保留最后错误。
    最小示例：可返回 ("C",1.2,180,"stop")。"""
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
