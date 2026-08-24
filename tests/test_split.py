"""测试模块：tests/test_split.py。

本文件验证项目中的一个具体行为或模块边界。测试输入通常是内存中的最小样例，测试输出是断言结果，不调用真实模型 API。

项目位置：tests/test_split.py。
主要用途：项目测试模块，验证公共基础层和三条评测线的行为、数据隔离与文档规范。
输入：输入来自测试夹具、临时目录和项目模块。
输出：输出为测试断言结果，不产生正式评测数据。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：通常只创建临时文件或调用测试替身，不调用真实模型 API。
"""

import unittest

from tracks.legal_benchmark.dataset.split import assign_case_splits


class SplitTests(unittest.TestCase):

    def test_assigns_case_level_stratified_splits_deterministically(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        cases = [
            {"case_id": f"contract_{i:02d}", "classification": {"primary_category": "合同、准合同纠纷"}}
            for i in range(10)
        ] + [
            {"case_id": f"labor_{i:02d}", "classification": {"primary_category": "劳动争议"}}
            for i in range(10)
        ]
        first = assign_case_splits(cases, seed=7)
        second = assign_case_splits(cases, seed=7)
        self.assertEqual(first, second)
        self.assertEqual(
            {row["split"] for row in first},
            {"dev", "calibration", "test"},
        )
        for category in ("合同、准合同纠纷", "劳动争议"):
            counts = {
                split: sum(
                    1
                    for row in first
                    if row["classification"]["primary_category"] == category
                    and row["split"] == split
                )
                for split in ("dev", "calibration", "test")
            }
            self.assertEqual(counts, {"dev": 3, "calibration": 2, "test": 5})

    def test_keeps_existing_case_split_for_all_questions(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        rows = [
            {"case_id": "case_1", "question_id": "q1"},
            {"case_id": "case_1", "question_id": "q2"},
            {"case_id": "case_2", "question_id": "q3"},
        ]
        result = assign_case_splits(rows, seed=1)
        split_by_case = {}
        for row in result:
            split_by_case.setdefault(row["case_id"], row["split"])
            self.assertEqual(split_by_case[row["case_id"]], row["split"])


if __name__ == "__main__":
    unittest.main()
