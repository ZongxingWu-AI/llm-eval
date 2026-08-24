"""法律分类词表访问模块。

项目位置：法律真实案例评测线的 taxonomy 包入口。
输入：同目录 taxonomy.json 以及待校验的题目标签、主分类和案由路径。
输出：受控标签集合、路径校验结果和规则推断的 cause_path。
上下游：解析、题集组装和验证模块共同依赖本模块，避免各自维护自由标签。
副作用：首次调用会读取并缓存 taxonomy.json；不写文件、不调用模型。"""

import json
from functools import lru_cache

from pathlib import Path

TAXONOMY_PATH = Path(__file__).resolve().parent / "taxonomy.json"


@lru_cache(maxsize=1)
def load_taxonomy() -> dict:
    """用途：读取并缓存法律 Benchmark 的受控分类词表。

    输入：无参数；固定读取同目录 taxonomy.json。
    输出：返回 taxonomy 字典，同一进程后续调用复用缓存。
    运行前数据形态：运行前 taxonomy 尚未加载。
    运行后数据变化：运行后得到分类、任务、能力、难度和评分方式等受控集合。
    副作用：首次调用读取本地 JSON 文件；不写文件、不调用模型。
    异常或失败处理：文件缺失或 JSON 非法时抛出异常，阻止使用不受控标签。"""

    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def allowed_values(field: str) -> set[str]:
    """用途：取得 taxonomy 顶层某字段允许使用的标签集合。

    输入：field 是如 task_types、difficulties 或 primary_categories 的字段名。
    输出：返回字符串集合；字段不存在或不是列表时返回空集合。
    运行前数据形态：输入是词表字段名。
    运行后数据变化：输出适合成员判断的 set。
    副作用：可能触发首次读取 taxonomy.json；不写文件、不调用模型。
    异常或失败处理：未知字段安全返回空集合。"""

    return set(load_taxonomy().get(field, []))


def validate_cause_path(primary_category: str, cause_path: list[str]) -> bool:
    """用途：检查案由路径是否属于指定主分类的受控树。

    输入：primary_category 是五类主分类之一；cause_path 是从大类到子案由的列表。
    输出：路径存在于 taxonomy 对应树时返回 True，否则 False。
    运行前数据形态：运行前路径可能由规则或模型生成。
    运行后数据变化：运行后得到可用于发布校验的布尔结果。
    副作用：读取 taxonomy 缓存，不修改输入、不写文件、不调用模型。
    异常或失败处理：分类不存在、路径类型错误、为空或层级不连续时返回 False。"""

    if not cause_path or cause_path[0] != primary_category:
        return False
    allowed = set(load_taxonomy()["cause_tree"].get(primary_category, []))
    for value in cause_path:
        is_primary_category = value == primary_category
        is_allowed_child = value in allowed
        if not is_primary_category and not is_allowed_child:
            return False
    return True


def infer_cause_path(text: str, category: str) -> list[str]:
    """用途：根据正文关键词在受控案由树中选择最具体路径。

    输入：text 是判决书全文；category 是已推断主分类。
    输出：返回以 category 开头的合法 cause_path 列表。
    运行前数据形态：运行前只有全文与主分类。
    运行后数据变化：运行后产生可被 validate_cause_path 复核的层级路径。
    副作用：读取 taxonomy.json；不写文件、不调用模型。
    异常或失败处理：无具体关键词时回退该分类默认叶子；未知分类返回仅含分类名的列表。"""

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
