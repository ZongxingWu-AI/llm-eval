"""法律 Benchmark 多维度题集管线的契约测试。

本文件只覆盖配置、按维度组装、题面校验、03 上下文组织、04 分维度报告和文档契约。
不修改或替代其他 agent 负责的 extraction/generation 测试，也不调用真实模型。
"""

import importlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

_build = importlib.import_module("methodology.02_构建题集.legal.dataset.build")
_validation = importlib.import_module("methodology.02_构建题集.legal.validation.validate")
_answer_run = importlib.import_module("methodology.03_模型作答.legal.evaluation.run")
_scoring_run = importlib.import_module("methodology.04_结果评测.legal.scoring.run")


class LegalDimensionPipelineTests(unittest.TestCase):
    """保护法律题集从维度定义到分维度报告的统一契约。"""

    def _classification(self, category="合同、准合同纠纷"):
        """构造受 taxonomy 约束的最小案件分类。"""
        return {
            "domain": "民事",
            "procedure_stage": "一审",
            "document_type": "判决书",
            "primary_category": category,
            "cause_path": [category, "买卖合同纠纷"] if category == "合同、准合同纠纷" else [category],
            "procedure_tags": [],
            "evidence_tags": ["书证"],
        }

    def _question(self, question_id, dimension_id, task_type, context_type, case_id=None):
        """构造可供 build 和 validation 使用的最小维度题目。"""
        case_id = case_id or f"case_{question_id}"
        return {
            "question_id": question_id,
            "case_id": case_id,
            "split": "test",
            "case_classification": self._classification(),
            "dimension_id": dimension_id,
            "task_type": task_type,
            "answer_type": "短答案",
            "context_type": context_type,
            "context": "卢某支付货款，合同约定付款期限为收到货物后十日内。",
            "scoring_method": "rule" if dimension_id == "fact_extraction" else "rubric_judge",
            "difficulty": "easy",
            "risk_level": "low",
            "question": "谁应当承担付款责任？",
            "reference_answer": "卢某应当承担付款责任。",
            "rubric": {"required_points": ["卢某"]},
            "source_evidence": [{"source_quote": "卢某支付货款"}],
            "review_status": "approved",
        }

    def test_catalog_has_nine_dimensions_and_expected_targets(self):
        """验证九类维度和蓝图目标均可由统一配置读取。"""
        config = importlib.import_module("methodology.02_构建题集.legal.config")
        catalog = config.load_dimension_catalog()
        dimensions = {item["dimension_id"]: item for item in catalog["dimensions"]}
        self.assertEqual(len(dimensions), 9)
        self.assertEqual(dimensions["procedure_time_reasoning"]["task_type"], "程序与时间推理")
        self.assertEqual(dimensions["compliance_refusal"]["default_context_type"], "scenario")
        targets = catalog["blueprint"]["dimension_targets"]
        self.assertEqual(sum(targets.values()), 300)
        self.assertEqual(targets["rule_application"], 60)

    def test_build_release_selects_candidates_by_dimension_quota(self):
        """验证正式题集按照 dimension_id 配额选择候选题，而不是按案件顺序截断。"""
        drafts = [
            self._question("q-fact", "fact_extraction", "事实抽取", "source_excerpt", "case_1"),
            self._question("q-rule", "rule_application", "法律规则适用", "self_contained", "case_2"),
        ]
        accepted, rejected, coverage = _build.build_release(
            drafts,
            blueprint={"dimension_quotas": {"fact_extraction": 1, "rule_application": 1}},
        )
        self.assertEqual(len(accepted), 2)
        self.assertEqual(rejected, [])
        self.assertEqual(coverage["dimension_counts"], {"fact_extraction": 1, "rule_application": 1})
        self.assertTrue(coverage["quota_satisfied"])

    def test_dimension_coverage_reports_quota_shortage(self):
        """验证候选题不足时输出明确的维度配额缺口。"""
        row = self._question("q-fact", "fact_extraction", "事实抽取", "source_excerpt")
        coverage = _build.dimension_coverage(
            [row], {"dimension_quotas": {"fact_extraction": 2, "rule_application": 1}},
        )
        self.assertEqual(coverage["quota_shortages"], {"dimension:fact_extraction": 1, "dimension:rule_application": 1})
        self.assertFalse(coverage["quota_satisfied"])

    def test_validation_rejects_judgment_prediction_answer_leak(self):
        """验证裁判结果预测题的 context 泄露法院结论时会被拒绝。"""
        row = self._question(
            "q-prediction", "judgment_prediction", "裁判结果预测", "source_excerpt", "case_prediction",
        )
        row["scoring_method"] = "rubric_judge"
        row["context"] = "案件材料如下。判决如下：支持原告的全部诉讼请求。"
        issues = _validation.check_row(row)
        self.assertTrue(any("泄露法院结论" in issue for issue in issues), issues)

    def test_model_input_uses_context_type_and_excludes_scoring_material(self):
        """验证 03 按四类 context_type 组织输入，且不把参考答案和 Rubric 发送给被测模型。"""
        for context_type in ("self_contained", "source_excerpt", "full_document", "scenario"):
            with self.subTest(context_type=context_type):
                row = {
                    "context_type": context_type,
                    "context": f"材料-{context_type}",
                    "question": "请回答具体问题。",
                    "reference_answer": "这是不应发送的参考答案。",
                    "rubric": {"required_points": ["隐藏评分点"]},
                    "source_evidence": [{"source_quote": "原文"}],
                }
                prompt = _answer_run._build_model_input(row)
                self.assertIn(row["context"], prompt)
                self.assertIn(row["question"], prompt)
                self.assertNotIn(row["reference_answer"], prompt)
                self.assertNotIn("隐藏评分点", prompt)

    def test_scoring_report_exposes_dimension_and_review_fields(self):
        """验证 04 报告至少提供按维度统计和人工复核入口。"""
        report = _scoring_run.build_report([
            {
                "question_id": "q-fact",
                "dimension_id": "fact_extraction",
                "context_type": "source_excerpt",
                "split": "test",
                "case_category": "合同、准合同纠纷",
                "task_type": "事实抽取",
                "difficulty": "easy",
                "risk_level": "low",
                "scoring_method": "rule",
                "verdict": "PASS",
            },
            {
                "question_id": "q-risk",
                "dimension_id": "compliance_refusal",
                "context_type": "scenario",
                "split": "test",
                "case_category": "侵权责任纠纷",
                "task_type": "合规拒答",
                "difficulty": "hard",
                "risk_level": "high",
                "scoring_method": "redline",
                "verdict": "REVIEW",
                "reason": "需要人工复核",
            },
        ])
        self.assertIn("按 dimension_id 统计", report)
        self.assertIn("fact_extraction", report)
        self.assertIn("compliance_refusal", report)
        self.assertIn("按风险等级统计", report)
        self.assertIn("人工复核清单", report)
        self.assertIn("q-risk", report)

    def test_teaching_documents_use_new_stage_order_and_decoupled_terms(self):
        """验证指定教学文档统一使用 03 模型作答、04 结果评测及解耦数据流。"""
        paths = [
            ROOT / "README.md",
            ROOT / "methodology" / "README.md",
            ROOT / "methodology" / "02_构建题集" / "README.md",
            ROOT / "methodology" / "02_构建题集" / "module_map.md",
            ROOT / "methodology" / "02_构建题集" / "learning_order.md",
            ROOT / "methodology" / "03_模型作答" / "README.md",
            ROOT / "methodology" / "03_模型作答" / "module_map.md",
            ROOT / "methodology" / "03_模型作答" / "learning_order.md",
            ROOT / "methodology" / "04_结果评测" / "README.md",
            ROOT / "methodology" / "04_结果评测" / "module_map.md",
            ROOT / "methodology" / "04_结果评测" / "learning_order.md",
            ROOT / "methodology" / "01_造Benchmark" / "legal" / "data" / "datasets" / "legal_20260827_001" / "releases" / "README.md",
            ROOT / "学习文档" / "13-手把手教你构建评测题集.md",
            ROOT / "学习文档" / "15-评测项目到底怎么跑-评测全流程拆解.md",
        ]
        merged = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        for phrase in ("dimension_id", "context", "legal_model_outputs.jsonl", "question_id", "事实抽取", "程序与时间推理"):
            self.assertIn(phrase, merged)
        legacy_stage_names = ("03 " + "\u5f53\u88c1\u5224", "04 " + "\u8dd1\u9879\u76ee")
        for phrase in legacy_stage_names:
            self.assertNotIn(phrase, merged)
        self.assertLess(merged.find("03 模型作答"), merged.find("04 结果评测"))


if __name__ == "__main__":
    unittest.main()
