"""法律 Benchmark 改造的自动化回归测试。"""

import importlib
import unittest
from hashlib import sha256

_validation = importlib.import_module("methodology.02_构建题集.legal.validation.validate")


def valid_row():
    """验证 valid_row 的预期行为。"""
    quote = "卢某支付货款"
    return {
        "question_id": "q-format", "case_id": "case-1", "split": "test",
        "case_classification": {"domain": "民事", "procedure_stage": "一审", "document_type": "判决书", "primary_category": "合同、准合同纠纷", "cause_path": ["合同、准合同纠纷", "买卖合同纠纷"], "procedure_tags": [], "evidence_tags": []},
        "dimension_id": "fact_extraction", "task_type": "事实抽取", "answer_type": "选项", "scoring_method": "rule", "difficulty": "easy", "risk_level": "low",
        "context_type": "source_excerpt", "context": "卢某支付货款。", "question": "谁支付货款？", "reference_answer": "卢某。", "rubric": {"required_points": ["卢某"]},
        "source_evidence": [{"source_quote": quote, "source_quote_sha256": sha256(quote.encode()).hexdigest()}],
        "question_format": "single_choice", "options": [{"option_id": x, "text": f"选项{x}"} for x in "ABCD"],
        "correct_option": "A", "distractor_rationales": {"B": "主体错误", "C": "事实遗漏", "D": "规则错误"}, "sample_tags": ["distractor"],
    }


class LegalQuestionFormatTests(unittest.TestCase):
    def test_removed_metadata_fields_are_not_required(self):
        """删除的题目元数据字段不应再参与合法性校验。"""
        row = valid_row()
        removed_fields = {"primary_" + "issue", "reasoning_" + "capabilities"}
        self.assertTrue(removed_fields.isdisjoint(row))
        self.assertFalse(any(any(field in x for field in removed_fields) for x in _validation.check_row(row)))

    def test_source_quote_hash_must_match(self):
        """验证 test_source_quote_hash_must_match 的预期行为。"""
        row = valid_row(); row["source_evidence"][0]["source_quote_sha256"] = "0" * 64
        self.assertTrue(any("sha256" in x or "哈希" in x for x in _validation.check_row(row)))

    def test_pair_validation_is_applied_by_batch_validate(self):
        """验证 test_pair_validation_is_applied_by_batch_validate 的预期行为。"""
        base = valid_row(); base["question_id"] = "base"; base["pair_id"] = "pair-1"; base["pair_role"] = "base"; base["sample_tags"] = ["minimal_pair", "counterfactual"]
        bad = dict(base); bad["question_id"] = "cf"; bad["pair_role"] = "base"
        findings = _validation.validate([base, bad])
        self.assertTrue(any("pair" in issue for f in findings for issue in f.get("issues", [])))


if __name__ == "__main__":
    unittest.main()

