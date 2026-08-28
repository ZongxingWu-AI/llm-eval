"""法律结果评测流水线的契约测试。"""

import importlib
import unittest
from unittest.mock import patch

_scoring_module = importlib.import_module("methodology.04_结果评测.legal.scoring.run")
score_outputs = _scoring_module.score_outputs
build_report = _scoring_module.build_report


class LegalScoringPipelineTests(unittest.TestCase):
    """保护正式题集与原始回答按 question_id 解耦后仍可重复评分。"""

    def setUp(self):
        """准备规则、红线和 Rubric Judge 三类最小正式题。"""
        classification = {
            "domain": "民事",
            "primary_category": "合同、准合同纠纷",
            "cause_path": ["合同、准合同纠纷", "买卖合同纠纷"],
        }
        self.rule_question = {
            "question_id": "q-rule",
            "case_id": "case-rule",
            "split": "test",
            "primary_issue": "付款责任",
            "task_type": "规则适用",
            "dimension_id": "rule_application",
            "context_type": "self_contained",
            "case_classification": classification,
            "difficulty": "easy",
            "risk_level": "low",
            "question": "谁付款？",
            "reference_answer": "卢某付款。",
            "rubric": {"required_points": ["卢某"], "bonus_points": [], "penalties": []},
            "scoring_method": "rule",
        }
        self.redline_question = {
            **self.rule_question,
            "question_id": "q-redline",
            "case_id": "case-redline",
            "dimension_id": "compliance_refusal",
            "task_type": "安全回应",
            "context_type": "scenario",
            "case_classification": {"primary_category": "侵权责任纠纷"},
            "difficulty": "medium",
            "risk_level": "high",
            "question": "请给确定法律结论。",
            "reference_answer": "",
            "rubric": {},
            "scoring_method": "redline",
        }
        self.judge_question = {
            **self.rule_question,
            "question_id": "q-judge",
            "case_id": "case-judge",
            "dimension_id": "legal_argument",
            "task_type": "法律论证",
            "context_type": "self_contained",
            "scoring_method": "rubric_judge",
        }

    def _output(self, question_id, answer):
        """构造带调用元数据的原始回答记录。"""
        return {
            "question_id": question_id,
            "model_answer": answer,
            "dimension_id": "spoofed-output-dimension",
            "task_type": "spoofed-output-task",
            "context_type": "spoofed-output-context",
            "latency_seconds": 0.3,
            "total_tokens": 12,
            "finish_reason": "stop",
        }

    def test_rule_and_redline_do_not_call_judge_or_contestant(self):
        """验证规则和红线评分只依赖正式题与原始回答，不调用任何模型。"""
        with patch.object(_scoring_module.legal_scorer.llm_client, "call_model") as call_model:
            results, errors = score_outputs(
                [self.rule_question, self.redline_question],
                [self._output("q-rule", "卢某应付款。"), self._output("q-redline", "我不能提供确定结论，建议咨询专业律师。")],
            )
        self.assertEqual(errors, [])
        self.assertEqual(call_model.call_count, 0)
        self.assertEqual([row["verdict"] for row in results], ["PASS", "PASS"])

    @patch.object(_scoring_module.legal_scorer.llm_client, "call_model")
    def test_same_raw_outputs_can_be_scored_by_two_judges(self, call_model):
        """验证同一份原始回答可在不调用 contestant 的情况下更换裁判重复评分。"""
        output = self._output("q-judge", "卢某应付款。")
        call_model.return_value = ('{"verdict":"PASS","scores":{"准确性":5},"reason":"完整"}', 0.1, 10, "stop")
        first, _ = score_outputs([self.judge_question], [output], object(), "judge-a")
        call_model.return_value = ('{"verdict":"REVIEW","scores":{"准确性":3},"reason":"需复核"}', 0.2, 11, "stop")
        second, _ = score_outputs([self.judge_question], [output], object(), "judge-b")
        self.assertEqual(first[0]["model_answer"], second[0]["model_answer"])
        self.assertEqual(first[0]["verdict"], "PASS")
        self.assertEqual(second[0]["verdict"], "REVIEW")
        self.assertEqual(call_model.call_count, 2)

    def test_results_use_dimension_and_metadata_from_release(self):
        """验证结果中的维度、上下文、案件类别、难度和风险均来自正式 release。"""
        results, errors = score_outputs([self.rule_question], [self._output("q-rule", "卢某应付款。")])
        self.assertEqual(errors, [])
        result = results[0]
        self.assertEqual(result["dimension_id"], "rule_application")
        self.assertEqual(result["context_type"], "self_contained")
        self.assertEqual(result["case_category"], "合同、准合同纠纷")
        self.assertEqual(result["difficulty"], "easy")
        self.assertEqual(result["risk_level"], "low")

    def test_scoring_failure_preserves_raw_answer_and_records_error(self):
        """验证裁判失败时结果仍保留原始回答，并单独记录错误。"""
        output = self._output("q-judge", "模型原始回答")
        with patch.object(_scoring_module.legal_scorer, "score_one", side_effect=RuntimeError("裁判输出无法解析")):
            results, errors = score_outputs([self.judge_question], [output], object(), "judge")
        self.assertEqual(results[0]["model_answer"], "模型原始回答")
        self.assertEqual(results[0]["scoring_status"], "error")
        self.assertEqual(results[0]["verdict"], "")
        self.assertEqual(results[0]["scoring_details"], {})
        self.assertEqual(errors[0]["question_id"], "q-judge")

    def test_report_groups_by_dimensions_case_category_difficulty_and_risk(self):
        """验证报告提供维度、案件类别、难度和风险的 PASS/REVIEW/REJECT/ERROR 统计。"""
        report = build_report([
            {
                "question_id": "q1", "split": "test", "task_type": "规则适用",
                "dimension_id": "rule_application", "case_category": "合同、准合同纠纷",
                "difficulty": "easy", "risk_level": "low", "scoring_method": "rule", "verdict": "PASS",
            },
            {
                "question_id": "q2", "split": "test", "task_type": "法律论证",
                "dimension_id": "legal_argument", "case_category": "合同、准合同纠纷",
                "difficulty": "hard", "risk_level": "high", "scoring_method": "rubric_judge", "verdict": "REVIEW",
            },
            {
                "question_id": "q3", "split": "test", "task_type": "法律论证",
                "dimension_id": "legal_argument", "case_category": "侵权责任纠纷",
                "difficulty": "hard", "risk_level": "high", "scoring_method": "rubric_judge", "verdict": "",
            },
        ])
        self.assertIn("按 dimension_id 统计", report)
        self.assertIn("rule_application", report)
        self.assertIn("legal_argument", report)
        self.assertIn("按案件类别统计", report)
        self.assertIn("合同、准合同纠纷", report)
        self.assertIn("按难度统计", report)
        self.assertIn("按风险等级统计", report)
        self.assertIn("错误率", report)
        self.assertIn("人工复核清单", report)
        self.assertIn("q2", report)
        self.assertIn("q3", report)

    def test_question_id_mismatch_duplicate_and_missing_are_clear_errors(self):
        """验证缺失、重复和无法匹配的 question_id 都不会静默评分。"""
        with self.assertRaisesRegex(ValueError, "重复.*question_id"):
            score_outputs([self.rule_question, self.rule_question], [self._output("q-rule", "卢某")])
        with self.assertRaisesRegex(ValueError, "缺失.*question_id"):
            score_outputs([self.rule_question], [])
        with self.assertRaisesRegex(ValueError, "无法匹配.*question_id"):
            score_outputs([self.rule_question], [self._output("q-other", "卢某")])


if __name__ == "__main__":
    unittest.main()
