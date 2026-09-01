"""法律 Benchmark 改造的自动化回归测试。"""

import importlib
import unittest

_run = importlib.import_module("methodology.04_结果评测.legal.scoring.run")


def rubric_row():
    """验证 rubric_row 的预期行为。"""
    return {"question_id": "q1", "case_id": "c1", "split": "test", "dimension_id": "legal_argument", "task_type": "法律论证", "question_format": "case_analysis", "context_type": "self_contained", "question": "说明理由", "reference_answer": "理由", "rubric": {"required_points": ["理由"]}, "scoring_method": "rubric_judge"}


class LegalErrorDiagnosisTests(unittest.TestCase):
    def test_missing_judge_is_scoring_error_and_preserves_answer(self):
        """验证 test_missing_judge_is_scoring_error_and_preserves_answer 的预期行为。"""
        results, errors = _run.score_outputs([rubric_row()], [{"question_id": "q1", "model_answer": "原始回答"}], None, None)
        self.assertEqual(len(errors), 1)
        self.assertEqual(results[0]["model_answer"], "原始回答")
        self.assertEqual(results[0]["scoring_status"], "error")
        self.assertEqual(results[0]["error_tags"], [])

    def test_report_contains_error_rate_and_review_list(self):
        """验证 test_report_contains_error_rate_and_review_list 的预期行为。"""
        results = [{"question_id": "q1", "dimension_id": "rule_application", "question_format": "case_analysis", "context_type": "self_contained", "split": "test", "case_category": "合同、准合同纠纷", "task_type": "法律规则适用", "difficulty": "hard", "risk_level": "high", "scoring_method": "rubric_judge", "verdict": "ERROR", "reason": "裁判输出无法解析", "error_tags": [], "scoring_status": "error"}]
        report = _run.build_report(results)
        self.assertIn("错误率", report)
        self.assertIn("人工复核", report)


if __name__ == "__main__":
    unittest.main()
