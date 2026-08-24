"""测试模块：tests/test_legal_validation.py。

本文件验证项目中的一个具体行为或模块边界。测试输入通常是内存中的最小样例，测试输出是断言结果，不调用真实模型 API。

项目位置：tests/test_legal_validation.py。
主要用途：项目测试模块，验证公共基础层和三条评测线的行为、数据隔离与文档规范。
输入：输入来自测试夹具、临时目录和项目模块。
输出：输出为测试断言结果，不产生正式评测数据。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：通常只创建临时文件或调用测试替身，不调用真实模型 API。
"""

import unittest

from tracks.legal_benchmark.validation.validate import check_row, validate

class LegalValidationTests(unittest.TestCase):

    def setUp(self):
        """为当前测试准备独立的临时目录、样例数据或 mock 环境。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        self.row = {
            "question_id": "q1", "case_id": "case_1", "split": "dev",
            "primary_issue": "付款责任", "task_type": "事实抽取",
            "reasoning_capabilities": ["事实抽取"], "answer_type": "短答案",
            "scoring_method": "rule", "difficulty": "easy", "risk_level": "low",
            "question": "谁付款？", "reference_answer": "卢某付款。",
            "rubric": {"required_points": ["卢某"]},
            "source_evidence": [{"source_section": "judgment", "source_quote": "卢某支付货款"}],
            "case_classification": {
                "domain": "民事", "procedure_stage": "一审", "document_type": "判决书",
                "primary_category": "合同、准合同纠纷",
                "cause_path": ["合同、准合同纠纷", "买卖合同纠纷"],
                "procedure_tags": [], "evidence_tags": ["书证"],
            },
        }
        self.case = {"case_id": "case_1", "sections": {"judgment": "判决如下：卢某支付货款。"}}

    def test_source_quote_must_exist_in_named_section(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        self.assertEqual(check_row(self.row, self.case), [])
        bad = {**self.row, "source_evidence": [{"source_section": "judgment", "source_quote": "任某支付货款"}]}
        self.assertTrue(any("无法" in issue for issue in check_row(bad, self.case)))

    def test_same_case_cannot_cross_splits(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        second = {**self.row, "question_id": "q2", "question": "第二题", "split": "test"}
        findings = validate([self.row, second], [self.case])
        self.assertTrue(any("同案跨 split" in issue for finding in findings for issue in finding["issues"]))


if __name__ == "__main__":
    unittest.main()
