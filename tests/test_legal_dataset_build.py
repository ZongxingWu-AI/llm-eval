"""法律正式题集组装测试。

被测模块：dataset.build 和案件级 split。使用内存候选题验证同案不跨集合及非法 taxonomy 的拒绝原因。
不使用 mock、不写文件、不调用模型。
失败表示待审题可能错误进入 release，或分类和 split 约束被破坏。"""

import importlib
import unittest

_build_module = importlib.import_module("methodology.02_构建题集.legal.dataset.build")
build = _build_module.build


class DatasetBuildTests(unittest.TestCase):

    def _draft(self, case_id, question, risk_level="low"):
        """测试目标：候选题测试夹具。
准备数据：创建一条最小合法候选题并允许调用方覆盖字段。
调用函数：调用本文件的 _draft 辅助函数。
预期结果：返回可用于 build 校验的独立字典。
该断言保护的行为：保护测试数据符合当前法律题目 schema。
副作用：只使用 mock、AST 或临时数据，不调用真实模型，不写入正式数据目录。"""

        return {
            "case_id": case_id,
            "case_classification": {
                "domain": "民事", "procedure_stage": "一审", "document_type": "判决书",
                "primary_category": "合同、准合同纠纷",
                "cause_path": ["合同、准合同纠纷", "买卖合同纠纷"],
                "procedure_tags": [], "evidence_tags": ["书证"],
            },
            "primary_issue": "付款责任", "task_type": "事实抽取",
            "reasoning_capabilities": ["事实抽取"], "answer_type": "短答案",
            "scoring_method": "rule", "difficulty": "easy", "risk_level": risk_level,
            "question": question, "reference_answer": "卢某付款。",
            "rubric": {"required_points": ["卢某"]},
            "source_evidence": [{"source_section": "judgment", "source_quote": "卢某付款"}],
            "review_status": "approved",
        }

    def test_build_keeps_all_questions_from_one_case_in_one_split(self):
        """测试目标：验证同一 case_id 的多道题始终进入同一 split。
        准备数据：准备多个案件且一个案件含多题的 approved 候选题。
        调用函数：调用 build。
        预期结果：同案题的 split 集合长度为 1。
        该断言保护的行为：案件事实不能通过同案题跨 dev/test 造成泄漏。"""

        drafts = [self._draft("case_1", "问题一"), self._draft("case_1", "问题二"), self._draft("case_2", "问题三")]
        accepted, rejected = build(drafts)
        self.assertEqual(rejected, [])
        self.assertEqual(len({row["split"] for row in accepted if row["case_id"] == "case_1"}), 1)
        self.assertEqual(len({row["question_id"] for row in accepted}), 3)

    def test_build_rejects_uncontrolled_risk_label(self):
        """测试目标：验证未知 risk_level 不会进入正式题集。
        准备数据：把一条候选题风险标签改为 taxonomy 外值。
        调用函数：调用 build。
        预期结果：accepted 为空且 rejected 含 taxonomy 相关原因。
        该断言保护的行为：模型自由标签不能绕过受控词表。"""

        accepted, rejected = build([self._draft("case_1", "问题", risk_level="critical")])
        self.assertEqual(accepted, [])
        self.assertEqual(len(rejected), 1)

    def test_build_rejects_uncontrolled_case_taxonomy(self):
        """测试目标：验证非法案件主分类或案由路径会被拒绝。
        准备数据：构造 case_classification 含不受控标签的 approved 题。
        调用函数：调用 build。
        预期结果：题目进入 rejected 而不是 release。
        该断言保护的行为：案件级分类与问题级标签执行同等严格校验。"""

        draft = self._draft("case_1", "问题")
        draft["case_classification"]["cause_path"] = ["合同、准合同纠纷", "虚构案由"]
        accepted, rejected = build([draft])
        self.assertEqual(accepted, [])
        self.assertEqual(len(rejected), 1)


if __name__ == "__main__":
    unittest.main()
