"""法律 Benchmark 新数据契约测试。"""
import importlib
import unittest

build_mod = importlib.import_module("methodology.02_构建题集.legal.dataset.build")
eval_mod = importlib.import_module("methodology.03_模型作答.legal.evaluation.run")
scorer = importlib.import_module("methodology.04_结果评测.legal.scoring.legal_scorer")


class NewLegalContractsTests(unittest.TestCase):
    def test_coverage_contains_format_dimension_and_tags(self):
        """验证覆盖报告包含题型、维度和专项标签统计。"""
        rows = [
            {"dimension_id": "rule_application", "question_format": "single_choice", "difficulty": "easy", "risk_level": "high", "sample_tags": ["distractor"]},
            {"dimension_id": "rule_application", "question_format": "case_analysis", "difficulty": "hard", "risk_level": "medium", "sample_tags": ["long_context"]},
        ]
        coverage = build_mod.dimension_coverage(rows, {
            "dimension_quotas": {"rule_application": 2},
            "question_format_quotas": {"single_choice": 1, "case_analysis": 1},
            "dimension_format_quotas": {"rule_application": {"single_choice": 1, "case_analysis": 1}},
            "difficulty_quotas": {"easy": 1, "hard": 1},
            "risk_quotas": {"high": 1, "medium": 1},
            "tag_minimums": {"distractor": 1, "long_context": 1},
        })
        self.assertEqual(coverage["question_format_counts"], {"single_choice": 1, "case_analysis": 1})
        self.assertEqual(coverage["dimension_format_counts"]["rule_application"]["case_analysis"], 1)
        self.assertFalse(coverage["incomplete"])

    def test_build_model_input_whitelists_options_and_excludes_gold(self):
        """验证 03 输入白名单只保留可见题面字段。"""
        prompt = eval_mod.build_model_input({
            "context_type": "self_contained", "context": "甲与乙签订合同。", "question": "谁承担付款责任？",
            "question_format": "single_choice", "options": [{"option_id": "A", "text": "甲"}, {"option_id": "B", "text": "乙"}],
            "reference_answer": "乙", "rubric": {"required_points": ["乙"]}, "correct_option": "B",
            "source_evidence": [{"source_quote": "乙"}], "full_text": "秘密原文",
        })
        self.assertIn("甲与乙签订合同", prompt)
        self.assertIn("A. 甲", prompt)
        self.assertNotIn("秘密原文", prompt)
        self.assertNotIn("required_points", prompt)
        self.assertNotIn("correct_option", prompt)

    def test_rule_scoring_supports_objective_formats(self):
        """验证规则评分支持首版客观题型。"""
        self.assertEqual(scorer.score_one({"scoring_method": "rule", "question_format": "single_choice", "correct_option": "B"}, "B")["verdict"], "PASS")
        self.assertEqual(scorer.score_one({"scoring_method": "rule", "question_format": "multiple_choice", "correct_options": ["A", "C"]}, "C,A")["verdict"], "PASS")
        self.assertEqual(scorer.score_one({"scoring_method": "rule", "question_format": "true_false", "correct_answer": True}, "是")["verdict"], "PASS")
        self.assertEqual(scorer.score_one({"scoring_method": "rule", "question_format": "numeric", "numeric_answer": 10, "numeric_tolerance": 0.1}, "10.05")["verdict"], "PASS")

    def test_diagnosis_marks_objective_error(self):
        """验证客观题错误可以生成诊断标签。"""
        result = scorer.diagnose_errors(
            {"question_format": "single_choice", "correct_option": "B", "error_targets": ["similar_concept_confusion"]},
            "A", {"verdict": "REJECT", "reason": "选项错误"},
        )
        self.assertIn("similar_concept_confusion", result["error_tags"])


if __name__ == "__main__":
    unittest.main()
