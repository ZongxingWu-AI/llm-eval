"""测试模块：tests/test_legal_dataset_build.py。

本文件验证项目中的一个具体行为或模块边界。测试输入通常是内存中的最小样例，测试输出是断言结果，不调用真实模型 API。

项目位置：tests/test_legal_dataset_build.py。
主要用途：项目测试模块，验证公共基础层和三条评测线的行为、数据隔离与文档规范。
输入：输入来自测试夹具、临时目录和项目模块。
输出：输出为测试断言结果，不产生正式评测数据。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：通常只创建临时文件或调用测试替身，不调用真实模型 API。
"""

import unittest

from tracks.legal_benchmark.dataset.build import build


class DatasetBuildTests(unittest.TestCase):

    def _draft(self, case_id, question, risk_level="low"):
        """为同一文件中的公开流程提供一个小而明确的辅助步骤。

参数：self、case_id、question、risk_level。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

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
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        drafts = [self._draft("case_1", "问题一"), self._draft("case_1", "问题二"), self._draft("case_2", "问题三")]
        accepted, rejected = build(drafts)
        self.assertEqual(rejected, [])
        self.assertEqual(len({row["split"] for row in accepted if row["case_id"] == "case_1"}), 1)
        self.assertEqual(len({row["question_id"] for row in accepted}), 3)

    def test_build_rejects_uncontrolled_risk_label(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        accepted, rejected = build([self._draft("case_1", "问题", risk_level="critical")])
        self.assertEqual(accepted, [])
        self.assertEqual(len(rejected), 1)

    def test_build_rejects_uncontrolled_case_taxonomy(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        draft = self._draft("case_1", "问题")
        draft["case_classification"]["cause_path"] = ["合同、准合同纠纷", "虚构案由"]
        accepted, rejected = build([draft])
        self.assertEqual(accepted, [])
        self.assertEqual(len(rejected), 1)


if __name__ == "__main__":
    unittest.main()
