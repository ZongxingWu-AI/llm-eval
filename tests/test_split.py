"""法律案件级数据划分测试。

被测模块：dataset.split.assign_case_splits。覆盖固定 seed 的分层比例、同案聚合和已有案件多题一致性。
全部使用内存字典，不写文件、不调用模型。
失败表示 dev/calibration/test 不可重复或发生同案泄漏。"""

import importlib
import unittest

_split_module = importlib.import_module("methodology.02_构建题集.legal.dataset.split")
assign_case_splits = _split_module.assign_case_splits


class SplitTests(unittest.TestCase):

    def test_assigns_case_level_stratified_splits_deterministically(self):
        """测试目标：验证每类十案按 3/2/5 分配且固定 seed 可重复。
        准备数据：构造五个主分类、每类十个不同 case_id。
        调用函数：两次调用 assign_case_splits。
        预期结果：两次结果一致，每类 dev=2、calibration=2、test=6。
        该断言保护的行为：正式报告的固定测试集不会随重复构建漂移。"""

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
            self.assertEqual(counts, {"dev": 2, "calibration": 2, "test": 6})

    def test_honors_explicit_split_ratios_at_case_level(self):
        """验证显式 split_ratios 按案件而非题目数量分配。"""
        rows = [
            {"case_id": f"case_{i:02d}", "case_classification": {"primary_category": "合同、准合同纠纷"}}
            for i in range(10)
        ]
        result = assign_case_splits(rows, seed=3, split_ratios={"dev": 0.2, "calibration": 0.2, "test": 0.6})
        counts = {split: sum(row["split"] == split for row in result) for split in ("dev", "calibration", "test")}
        self.assertEqual(counts, {"dev": 2, "calibration": 2, "test": 6})

    def test_keeps_existing_case_split_for_all_questions(self):
        """测试目标：验证一个案件生成多题时所有题共享案件级 split。
        准备数据：构造同一 case_id 的多条问题记录。
        调用函数：调用 assign_case_splits。
        预期结果：这些题目的 split 集合只有一个值。
        该断言保护的行为：问题数量不会让同案跨集合泄漏。"""

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
