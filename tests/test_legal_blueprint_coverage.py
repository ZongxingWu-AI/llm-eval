"""法律 Benchmark 改造的自动化回归测试。"""

import importlib
import unittest
from pathlib import Path
import tempfile

_build = importlib.import_module("methodology.02_构建题集.legal.dataset.build")


class LegalBlueprintCoverageTests(unittest.TestCase):
    def test_coverage_reports_case_type_and_split_shortages(self):
        """验证 test_coverage_reports_case_type_and_split_shortages 的预期行为。"""
        blueprint = {
            "target_total": 2,
            "dimension_quotas": {"fact_extraction": 2},
            "case_type_minimum_counts": {"劳动争议": 1, "侵权责任纠纷": 1},
            "split_ratios": {"dev": 0.5, "test": 0.5},
        }
        rows = [{"dimension_id": "fact_extraction", "question_format": "structured_extraction", "difficulty": "easy", "risk_level": "low", "sample_tags": [], "case_id": "case-1", "case_classification": {"primary_category": "合同、准合同纠纷"}, "split": "test"}]
        coverage = _build.dimension_coverage(rows, blueprint)
        self.assertIn("case_type_shortages", coverage)
        self.assertIn("case_type:劳动争议", coverage["quota_shortages"])
        self.assertIn("split_counts", coverage)
        self.assertTrue(coverage["incomplete"])

    def test_coverage_report_includes_matrix_case_and_split_sections(self):
        """验证覆盖报告完整展示矩阵、案件类别和 split 实际/目标。"""
        blueprint = {
            "target_total": 2,
            "dimension_quotas": {"fact_extraction": 1, "rule_application": 1},
            "question_format_quotas": {"structured_extraction": 1, "case_analysis": 1},
            "dimension_format_quotas": {"fact_extraction": {"structured_extraction": 1}},
            "split_ratios": {"dev": 0.5, "test": 0.5},
        }
        rows = [
            {"question_id": "q1", "dimension_id": "fact_extraction", "question_format": "structured_extraction", "difficulty": "easy", "risk_level": "low", "sample_tags": [], "case_id": "case-1", "case_classification": {"primary_category": "合同、准合同纠纷"}, "split": "dev"},
            {"question_id": "q2", "dimension_id": "rule_application", "question_format": "case_analysis", "difficulty": "medium", "risk_level": "medium", "sample_tags": [], "case_id": "case-2", "case_classification": {"primary_category": "劳动争议"}, "split": "test"},
        ]
        coverage = _build.dimension_coverage(rows, blueprint)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "coverage.md"
            _build._write_coverage_report(path, coverage, [])
            report = path.read_text(encoding="utf-8")
        self.assertIn("## 案件类别", report)
        self.assertIn("## Split", report)
        self.assertIn("## 维度 × 题型矩阵", report)
        self.assertIn("| fact_extraction | 1 | 1 | 0 |", report)
        self.assertIn("合同、准合同纠纷", report)

    def test_max_items_cannot_hide_blueprint_incompleteness(self):
        """验证 test_max_items_cannot_hide_blueprint_incompleteness 的预期行为。"""
        blueprint = {"target_total": 2, "dimension_quotas": {"fact_extraction": 2}}
        rows = [{"dimension_id": "fact_extraction", "question_format": "structured_extraction", "difficulty": "easy", "risk_level": "low", "sample_tags": [], "case_id": "case-1", "case_classification": {"primary_category": "合同、准合同纠纷"}, "split": "test"}, {"dimension_id": "fact_extraction", "question_format": "structured_extraction", "difficulty": "easy", "risk_level": "low", "sample_tags": [], "case_id": "case-2", "case_classification": {"primary_category": "合同、准合同纠纷"}, "split": "test"}]
        coverage = _build.dimension_coverage(rows[:1], blueprint)
        self.assertEqual(coverage["quota_shortages"]["total"], 1)

    def test_selector_prioritizes_unmet_secondary_coverage_deterministically(self):
        """主配额相同的候选中，优先补足难度、风险、标签、案件类别和 split。"""
        blueprint = {
            "target_total": 2,
            "dimension_quotas": {"rule_application": 2},
            "question_format_quotas": {"case_analysis": 2},
            "difficulty_quotas": {"hard": 2},
            "risk_quotas": {"high": 2},
            "tag_minimums": {"adversarial": 1},
            "case_type_minimum_counts": {"劳动争议": 1, "侵权责任纠纷": 1},
            "split_targets": {"dev": 1, "test": 1},
        }
        candidates = [
            {
                "question_id": "q-a",
                "dimension_id": "rule_application",
                "question_format": "case_analysis",
                "difficulty": "hard",
                "risk_level": "high",
                "sample_tags": [],
                "case_id": "case-contract",
                "case_classification": {"primary_category": "合同、准合同纠纷"},
                "split": "dev",
                "question": "A baseline",
            },
            {
                "question_id": "q-b",
                "dimension_id": "rule_application",
                "question_format": "case_analysis",
                "difficulty": "hard",
                "risk_level": "high",
                "sample_tags": ["adversarial"],
                "case_id": "case-labor",
                "case_classification": {"primary_category": "劳动争议"},
                "split": "test",
                "question": "B adversarial",
            },
            {
                "question_id": "q-c",
                "dimension_id": "rule_application",
                "question_format": "case_analysis",
                "difficulty": "hard",
                "risk_level": "high",
                "sample_tags": [],
                "case_id": "case-tort",
                "case_classification": {"primary_category": "侵权责任纠纷"},
                "split": "dev",
                "question": "C tort",
            },
        ]

        selected, rejected = _build._select_with_quotas(candidates, blueprint)
        selected_again, _ = _build._select_with_quotas(list(reversed(candidates)), blueprint)

        self.assertEqual({row["question_id"] for row in selected}, {"q-b", "q-c"})
        self.assertEqual(
            [row["question_id"] for row in selected],
            [row["question_id"] for row in selected_again],
        )
        self.assertEqual({row["question_id"] for row in rejected}, {"q-a"})


if __name__ == "__main__":
    unittest.main()
