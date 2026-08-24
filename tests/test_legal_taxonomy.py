"""法律案由 taxonomy 测试。

被测模块：taxonomy.infer_cause_path 与 validate_cause_path。使用内存文本检查无关键词时的默认叶子仍在受控树中。
不使用 mock、不写文件、不调用模型。
失败表示规则分类可能生成无法通过发布校验的案由路径。"""

import unittest

from tracks.legal_benchmark.taxonomy import infer_cause_path, validate_cause_path



class CausePathTests(unittest.TestCase):
    def test_default_leaf_is_in_controlled_taxonomy(self):
        """测试目标：验证无具体关键词时推断的默认案由仍属于受控 taxonomy。
        准备数据：为五个主分类分别准备无特征文本。
        调用函数：调用 infer_cause_path 后再调用 validate_cause_path。
        预期结果：每条默认路径都返回合法。
        该断言保护的行为：解析器回退规则不会生成无法发布的分类。"""

        for category in (
            "合同、准合同纠纷",
            "劳动争议",
            "侵权责任纠纷",
            "婚姻家庭、继承纠纷",
            "物权纠纷",
        ):
            path = infer_cause_path("没有出现具体案由关键词", category)
            self.assertTrue(validate_cause_path(category, path), path)


if __name__ == "__main__":
    unittest.main()
