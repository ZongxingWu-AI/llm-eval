"""法律题目分类字段兼容测试。

被测模块：dataset.split 对 generation 题目 case_classification 的读取。使用内存候选题验证按案件主分类分层。
不使用 mock、不写文件、不调用模型。
失败表示题集组装可能把所有候选题错误归入“未分类”。"""

import unittest

from tracks.legal_benchmark.dataset.split import assign_case_splits


class SplitCaseClassificationTests(unittest.TestCase):

    def test_stratifies_generated_questions_using_case_classification(self):
        """测试目标：验证候选题使用 case_classification.primary_category 参与分层。
        准备数据：构造多个分类下的 generation 格式问题。
        调用函数：调用 assign_case_splits。
        预期结果：分类被正确读取并按案件分配，不全部落入未分类组。
        该断言保护的行为：生成阶段到题集阶段的分类字段兼容。"""

        rows = []
        for category in ("合同、准合同纠纷", "劳动争议"):
            for index in range(10):
                rows.append({
                    "case_id": f"{category}_{index}",
                    "question_id": f"q_{category}_{index}",
                    "case_classification": {"primary_category": category},
                })
        result = assign_case_splits(rows, seed=9)
        for category in ("合同、准合同纠纷", "劳动争议"):
            counts = {
                split: sum(1 for row in result if row["case_classification"]["primary_category"] == category and row["split"] == split)
                for split in ("dev", "calibration", "test")
            }
            self.assertEqual(counts, {"dev": 3, "calibration": 2, "test": 5})


if __name__ == "__main__":
    unittest.main()
