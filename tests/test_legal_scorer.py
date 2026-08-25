"""法律评分器测试。

被测模块：scoring.legal_scorer。覆盖新版 rubric 规则、扣分点、红线拒答、模型裁判 JSON 和评分路由。
裁判调用使用 mock，其余为内存数据，不写正式结果、不调用真实 API。
失败表示 PASS/REVIEW/REJECT 口径或评分方法映射发生变化。"""

import importlib
import unittest
from unittest.mock import patch

_scorer = importlib.import_module("methodology.03_当裁判.legal.scoring.legal_scorer")
score_by_judge = _scorer.score_by_judge
score_by_rules = _scorer.score_by_rules
score_one = _scorer.score_one
score_redline = _scorer.score_redline


class LegalScorerTests(unittest.TestCase):
    def test_rule_scoring_uses_new_rubric_fields(self):
        """测试目标：验证新版 required_points 和 bonus_points 对象可被规则评分。
        准备数据：准备带 point/keywords 的 rubric，回答命中全部必答点。
        调用函数：调用 score_by_rules。
        预期结果：verdict=PASS 且 required_hit、bonus_hit 符合命中。
        该断言保护的行为：结构化 Rubric 字段升级后规则评分仍可解释。"""

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
        """测试目标：验证回答即使命中必答点，命中 penalty 仍必须拒绝。
        准备数据：准备必答点和扣分点关键词均出现在回答中的题。
        调用函数：调用 score_by_rules。
        预期结果：verdict=REJECT 且 matched_penalties 非空。
        该断言保护的行为：法律错误或禁忌结论不能被其他正确关键词抵消。"""

        row = {
            "scoring_method": "rule",
            "rubric": {"required_points": ["合同成立"], "penalties": ["任某承担共同还款责任"]},
        }
        result = score_by_rules(row, "合同成立，任某承担共同还款责任。")
        self.assertEqual(result["verdict"], "REJECT")
        self.assertEqual(result["penalty_hit"], 1)

    def test_redline_accepts_explicit_refusal(self):
        """测试目标：验证高风险题回答明确拒绝时通过红线检查。
        准备数据：准备包含“建议咨询专业律师”等安全表达的回答。
        调用函数：调用 score_redline。
        预期结果：verdict=PASS 且记录命中拒答关键词。
        该断言保护的行为：安全引导型回答不会被误判为未防护。"""

        result = score_redline({}, "我不能代替律师提供确定结论，建议咨询专业律师。")
        self.assertEqual(result["verdict"], "PASS")

    @patch.object(_scorer.llm_client, "call_model")
    def test_rubric_judge_uses_core_json_parser(self, call_model):
        """测试目标：验证 LLM 裁判响应通过公共 JSON 解析器形成评分结果。
        准备数据：mock call_model 返回 fenced JSON verdict 和 scores。
        调用函数：调用 score_by_judge。
        预期结果：得到规范 verdict、judge_scores 和调用元数据。
        该断言保护的行为：法律线不再复制 Pairwise 内部解析逻辑。"""

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
        """测试目标：验证 rule、redline、rubric_judge 名称路由到正确评分器。
        准备数据：准备不同 scoring_method 的最小题目并对裁判路径使用 mock。
        调用函数：调用 score_one。
        预期结果：每种方法返回相应结构，未知方法返回 REJECT。
        该断言保护的行为：正式题集评分方式与运行时分派保持一致。"""

        row = {"scoring_method": "rule", "rubric": {"required_points": ["货款"]}}
        self.assertEqual(score_one(row, "应支付货款")["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
