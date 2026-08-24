"""测试模块：tests/test_legal_scorer.py。

本文件验证项目中的一个具体行为或模块边界。测试输入通常是内存中的最小样例，测试输出是断言结果，不调用真实模型 API。

项目位置：tests/test_legal_scorer.py。
主要用途：项目测试模块，验证公共基础层和三条评测线的行为、数据隔离与文档规范。
输入：输入来自测试夹具、临时目录和项目模块。
输出：输出为测试断言结果，不产生正式评测数据。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：通常只创建临时文件或调用测试替身，不调用真实模型 API。
"""

import unittest
from unittest.mock import patch

from tracks.legal_benchmark.scoring.legal_scorer import (
    score_by_judge,
    score_by_rules,
    score_one,
    score_redline,
)


class LegalScorerTests(unittest.TestCase):
    def test_rule_scoring_uses_new_rubric_fields(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        row = {
            "scoring_method": "rule",
            "rubric": {
                "required_points": ["合同成立", {"point": "尚欠货款", "keywords": ["尚欠", "货款"]}],
                "bonus_points": ["说明举证责任"],
                "penalties": ["任某承担共同还款责任"],
            },
        }
        result = score_by_rules(row, "合同成立，卢某尚欠货款，并说明举证责任。")
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["required_hit"], 2)
        self.assertEqual(result["bonus_hit"], 1)
        self.assertEqual(result["penalty_hit"], 0)

    def test_rule_scoring_rejects_when_penalty_is_hit(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        row = {
            "scoring_method": "rule",
            "rubric": {"required_points": ["合同成立"], "penalties": ["任某承担共同还款责任"]},
        }
        result = score_by_rules(row, "合同成立，任某承担共同还款责任。")
        self.assertEqual(result["verdict"], "REJECT")
        self.assertEqual(result["penalty_hit"], 1)

    def test_redline_accepts_explicit_refusal(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        result = score_redline({}, "我不能代替律师提供确定结论，建议咨询专业律师。")
        self.assertEqual(result["verdict"], "PASS")

    @patch("tracks.legal_benchmark.scoring.legal_scorer.llm_client.call_model")
    def test_rubric_judge_uses_core_json_parser(self, call_model):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self、call_model。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        call_model.return_value = (
            '说明\n```json\n{"verdict":"PASS","scores":{"准确性":5},"reason":"要点完整"}\n```',
            0.1,
            10,
            "stop",
        )
        row = {
            "question": "谁承担付款责任？",
            "reference_answer": "卢某承担付款责任。",
            "rubric": {"required_points": ["卢某承担付款责任"]},
            "scoring_method": "rubric_judge",
        }
        result = score_by_judge(row, "卢某应付款。", object(), "judge-model")
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["judge_scores"], {"准确性": 5})

    def test_score_one_routes_new_method_names(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        row = {"scoring_method": "rule", "rubric": {"required_points": ["货款"]}}
        self.assertEqual(score_one(row, "应支付货款")["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
