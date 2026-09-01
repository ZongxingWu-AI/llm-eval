"""法律 Benchmark 多维度配置与题目契约测试。

本文件只覆盖 Task 1 的配置/schema/taxonomy 契约，不触及出题、组装、校验或模型作答实现。
"""

import json
import importlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "methodology" / "01_造Benchmark" / "legal" / "schemas" / "question.schema.json"
TAXONOMY_PATH = ROOT / "methodology" / "01_造Benchmark" / "legal" / "taxonomy" / "taxonomy.json"

EXPECTED_DIMENSIONS = {
    "fact_extraction": "事实抽取",
    "issue_identification": "争议焦点识别",
    "rule_application": "法律规则适用",
    "evidence_evaluation": "证据评价",
    "judgment_prediction": "裁判结果预测",
    "legal_argument": "法律论证",
    "amount_calculation": "金额计算",
    "compliance_refusal": "合规拒答",
    "procedure_time_reasoning": "程序与时间推理",
}
EXPECTED_CONTEXT_TYPES = {"source_excerpt", "full_document", "self_contained", "scenario"}
REQUIRED_DIMENSION_FIELDS = {
    "dimension_id",
    "task_type",
    "applicable_case_types",
    "target_count",
    "context_types",
    "default_context_type",
    "scoring_method",
    "prompt_template",
    "required_answer_points",
    "difficulty_distribution",
    "risk_distribution",
}


class LegalDimensionConfigTests(unittest.TestCase):
    def test_catalog_exposes_nine_unique_dimensions_and_blueprint(self):
        """执行法律评测测试。"""
        config = importlib.import_module("methodology.02_构建题集.legal.config")
        catalog = config.load_dimension_catalog()

        self.assertEqual(set(EXPECTED_DIMENSIONS), {item["dimension_id"] for item in catalog["dimensions"]})
        self.assertEqual(len(catalog["dimensions"]), len({item["dimension_id"] for item in catalog["dimensions"]}))
        self.assertIn("blueprint", catalog)
        self.assertIsInstance(catalog["blueprint"], dict)

    def test_each_dimension_has_required_fields_and_valid_context_distribution(self):
        """执行法律评测测试。"""
        config = importlib.import_module("methodology.02_构建题集.legal.config")
        catalog = config.load_dimension_catalog()

        for dimension in catalog["dimensions"]:
            self.assertTrue(REQUIRED_DIMENSION_FIELDS <= set(dimension), dimension["dimension_id"])
            self.assertEqual(EXPECTED_DIMENSIONS[dimension["dimension_id"]], dimension["task_type"])
            self.assertGreater(dimension["target_count"], 0)
            self.assertTrue(set(dimension["context_types"]) <= EXPECTED_CONTEXT_TYPES)
            self.assertIn(dimension["default_context_type"], dimension["context_types"])
            self.assertIn(dimension["scoring_method"], {"rule", "redline", "rubric_judge"})
            self.assertTrue(dimension["prompt_template"].endswith(".md"))
            self.assertTrue(dimension["required_answer_points"])
            self.assertAlmostEqual(sum(dimension["difficulty_distribution"].values()), 1.0)
            self.assertAlmostEqual(sum(dimension["risk_distribution"].values()), 1.0)

    def test_get_dimension_returns_mapping_and_rejects_unknown_id(self):
        """执行法律评测测试。"""
        config = importlib.import_module("methodology.02_构建题集.legal.config")

        self.assertEqual(config.get_dimension("procedure_time_reasoning")["task_type"], "程序与时间推理")
        with self.assertRaises(KeyError):
            config.get_dimension("not_a_legal_dimension")

    def test_taxonomy_contains_expected_tasks(self):
        """执行法律评测测试。"""
        taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))

        self.assertIn("程序与时间推理", taxonomy["task_types"])
        self.assertIn("法律规则适用", taxonomy["task_types"])
        self.assertIn("争议焦点识别与规则适用", taxonomy["task_types"])
        self.assertNotIn("reasoning_" + "capabilities", taxonomy)

    def test_question_schema_requires_dimension_context_and_traceable_evidence(self):
        """执行法律评测测试。"""
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

        self.assertFalse(schema["additionalProperties"])
        self.assertTrue({"dimension_id", "context_type", "context"} <= set(schema["required"]))
        self.assertEqual(
            set(schema["properties"]["dimension_id"]["enum"]),
            set(EXPECTED_DIMENSIONS),
        )
        self.assertEqual(
            set(schema["properties"]["context_type"]["enum"]),
            EXPECTED_CONTEXT_TYPES,
        )
        evidence_schema = schema["properties"]["source_evidence"]
        self.assertEqual(evidence_schema["items"]["type"], "object")
        self.assertEqual(
            set(evidence_schema["items"]["required"]),
            {"source_quote"},
        )

    def test_dimensions_use_only_declared_fields(self):
        """维度配置不再定义已删除的能力元数据。"""
        config = importlib.import_module("methodology.02_构建题集.legal.config")
        catalog = config.load_dimension_catalog()
        for dimension in catalog["dimensions"]:
            self.assertNotIn("reasoning_" + "capabilities", dimension)



if __name__ == "__main__":
    unittest.main()
