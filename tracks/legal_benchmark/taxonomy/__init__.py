"""Python 包初始化模块：tracks/legal_benchmark/taxonomy/__init__.py。

本文件用于标记目录为可导入的 Python 包，不执行评测业务逻辑。

项目位置：tracks/legal_benchmark/taxonomy/__init__.py。
主要用途：法律真实案例 Benchmark，负责判决书解析、结构化提取、出题、校验和法律评测。
输入：输入来自法律线 data/raw、parsed、cleaned、drafts、releases 或 taxonomy/schema。
输出：输出按生命周期写入法律线对应 data 子目录或 results 目录。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：ingestion/extraction/generation/evaluation 可能写文件；只有带模型选项时才调用模型。
"""

import json
from functools import lru_cache

from pathlib import Path

TAXONOMY_PATH = Path(__file__).resolve().parent / "taxonomy.json"


@lru_cache(maxsize=1)
def load_taxonomy() -> dict:
    """完成当前模块中的一个处理步骤。

参数：无。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def allowed_values(field: str) -> set[str]:
    """完成当前模块中的一个处理步骤。

参数：field。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    return set(load_taxonomy().get(field, []))


def validate_cause_path(primary_category: str, cause_path: list[str]) -> bool:
    """完成当前模块中的一个处理步骤。

参数：primary_category、cause_path。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    if not cause_path or cause_path[0] != primary_category:
        return False
    allowed = set(load_taxonomy()["cause_tree"].get(primary_category, []))
    return all(value == primary_category or value in allowed for value in cause_path)


def infer_cause_path(text: str, category: str) -> list[str]:
    """根据案件文本和一级分类推断一个受控的案由路径。

    参数：
        text：判决书全文或标题中的可检索文本。
        category：taxonomy.json 中的一级分类。
    返回：
        形如 ``[一级分类, 具体案由]`` 的列表；无法识别具体案由时使用
        该分类下的“其他”案由。未知分类返回空列表。
    副作用：不调用模型、不写文件，只读取已经缓存的 taxonomy。

    示例：
        ``infer_cause_path("买卖合同纠纷", "合同、准合同纠纷")``
        返回 ``["合同、准合同纠纷", "买卖合同纠纷"]``。
    """

    cause_tree = load_taxonomy().get("cause_tree", {})
    leaves = cause_tree.get(category, [])
    if not leaves:
        return []

    keyword_rules = {
        "合同、准合同纠纷": (("买卖", "买卖合同纠纷"), ("借款", "民间借贷纠纷"),
                          ("租赁", "租赁合同纠纷"), ("服务", "服务合同纠纷"),
                          ("劳务", "劳务合同纠纷")),
        "劳动争议": (("劳动关系", "确认劳动关系纠纷"), ("工资", "劳动报酬纠纷"),
                    ("解除", "解除劳动合同纠纷"), ("经济补偿", "经济补偿金纠纷"),
                    ("工伤", "工伤保险待遇纠纷")),
        "侵权责任纠纷": (("交通事故", "机动车交通事故责任纠纷"), ("医疗", "医疗损害责任纠纷"),
                        ("产品", "产品责任纠纷"), ("安全保障", "违反安全保障义务责任纠纷"),
                        ("人身损害", "人身损害赔偿纠纷")),
        "婚姻家庭、继承纠纷": (("离婚后财产", "离婚后财产纠纷"), ("离婚", "离婚纠纷"),
                              ("抚养", "抚养纠纷"), ("继承", "继承纠纷"),
                              ("共同债务", "夫妻共同债务纠纷")),
        "物权纠纷": (("所有权确认", "所有权确认纠纷"), ("返还原物", "返还原物纠纷"),
                    ("排除妨害", "排除妨害纠纷"), ("相邻", "相邻关系纠纷"),
                    ("房屋", "房屋所有权纠纷")),
    }
    selected = ""
    for keyword, label in keyword_rules.get(category, ()):
        if keyword in text:
            selected = label
            break
    if selected not in leaves:
        selected = leaves[-1]
    return [category, selected]
