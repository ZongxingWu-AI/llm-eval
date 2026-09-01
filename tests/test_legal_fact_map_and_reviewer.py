"""事实地图 canonical 契约、抽取门禁和独立 Reviewer 的回归测试。"""

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import llm_client

_extract = importlib.import_module("methodology.01_造Benchmark.legal.extraction.extract")
_generate = importlib.import_module("methodology.02_构建题集.legal.generation.generate")


class CanonicalFactMapTests(unittest.TestCase):
    def _case(self):
        """构造包含脱敏全文和抽取状态的最小测试案件。"""
        return {
            "case_id": "case_canonical",
            "external_text": "原告甲起诉被告乙支付货款。法院认定送货单真实。判决被告乙支付货款。",
        }

    def _valid_map(self):
        """构造每个事实地图字段齐全且引用可回查的测试结果。"""
        groups = list(_extract.FACT_MAP_GROUPS)
        return {
            "case_fact_map": {
                group: [{
                "text": "法院认定送货单真实。",
                "source_quote": "法院认定送货单真实。",
            }] if group == "evidence" else []
                for group in groups
            }
        }

    def test_llm_fact_map_is_canonical_and_ready(self):
        """验证完整事实地图通过引用校验后进入可出题状态。"""
        case = self._case()
        candidate = self._valid_map()
        with patch.object(_extract.llm_client, "call_model", return_value=(json.dumps(candidate), 0, 0, "stop")), \
             patch.object(_extract, "load_template", return_value="template"), \
             patch.object(_extract, "render", return_value="prompt"):
            result = _extract.extract_case(case, client=object(), model="extractor-model")

        extraction = result["legal_extraction"]
        self.assertEqual(set(extraction["case_fact_map"]), set(_extract.FACT_MAP_GROUPS))
        self.assertEqual(result["quality"]["extraction"]["method"], "llm_grounded")
        self.assertEqual(result["quality"]["extraction"]["review_status"], "ready_for_generation")
        entry = extraction["case_fact_map"]["evidence"][0]
        self.assertEqual(
            entry["source_quote_sha256"],
            _extract.hashlib.sha256("法院认定送货单真实。".encode("utf-8")).hexdigest(),
        )

    def test_incomplete_llm_map_is_rules_fallback_and_needs_review(self):
        """验证不完整模型抽取降级为待复核且不伪造专家确认。"""
        case = self._case()
        candidate = {"case_fact_map": {"evidence": [{
            "text": "法院认定送货单真实。",
            "source_quote": "法院认定送货单真实。",
        }]}}
        with patch.object(_extract.llm_client, "call_model", return_value=(json.dumps(candidate), 0, 0, "stop")), \
             patch.object(_extract, "load_template", return_value="template"), \
             patch.object(_extract, "render", return_value="prompt"):
            result = _extract.extract_case(case, client=object(), model="extractor-model")

        quality = result["quality"]["extraction"]
        self.assertEqual(quality["method"], "rules_fallback")
        self.assertEqual(quality["review_status"], "needs_review")
        self.assertNotEqual(quality.get("status"), "expert_confirmed")


class GenerationExtractionGateTests(unittest.TestCase):
    def test_needs_review_case_is_blocked_before_model_client_is_created(self):
        """验证待复核案件在创建出题客户端前被门禁拦截。"""
        case = {
            "case_id": "case_blocked",
            "quality": {"extraction": {"method": "rules_fallback", "review_status": "needs_review"}},
            "legal_extraction": {"case_fact_map": {group: [] for group in _extract.FACT_MAP_GROUPS}},
            "external_text": "案件材料",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "cases.jsonl"
            output_path = root / "drafts.jsonl"
            input_path.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
            with patch.object(_generate.llm_client, "load_env"), \
                 patch.object(_generate.llm_client, "read_role") as read_role, \
                 patch.object(_generate.llm_client, "build_client") as build_client:
                rows = _generate.run(input_path, output_path, questions_per_case=1)
                errors_text = output_path.with_suffix(".errors.jsonl").read_text(encoding="utf-8")

        self.assertEqual(rows, [])
        read_role.assert_not_called()
        build_client.assert_not_called()
        self.assertIn("needs_review", errors_text)


class ReviewerIsolationTests(unittest.TestCase):
    def test_explicit_reviewer_does_not_fallback_to_deepseek(self):
        """验证 Reviewer 缺配置时不回退到通用 DeepSeek 配置。"""
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "deepseek-key",
            "DEEPSEEK_BASE_URL": "https://deepseek.example",
            "REVIEWER_API_KEY": "",
            "REVIEWER_BASE_URL": "",
            "REVIEWER_MODEL": "",
        }, clear=False):
            with self.assertRaises(ValueError):
                llm_client.read_explicit_role("REVIEWER")

    def test_reviewer_same_identity_as_generator_is_rejected(self):
        """验证 Generator 与 Reviewer 使用同一身份时被拒绝。"""
        with self.assertRaises(ValueError):
            llm_client.ensure_roles_distinct(
                ("https://api.example/v1", "generator"),
                ("https://api.example/v1/", "generator"),
            )


class ReviewerRunIsolationTests(unittest.TestCase):
    """验证题集 Reviewer 运行时的显式配置和输入白名单。"""

    def _question(self):
        """构造一条供 Reviewer 复核的最小候选题。"""
        return {
            "question_id": "q-reviewer",
            "case_id": "case-reviewer",
            "split": "dev",
            "dimension_id": "fact_extraction",
            "task_type": "事实抽取",
            "question_format": "single_choice",
            "answer_type": "选项",
            "scoring_method": "rule",
            "difficulty": "easy",
            "risk_level": "low",
            "context_type": "source_excerpt",
            "context": "原告甲提交送货单。",
            "question": "谁提交了送货单？",
            "options": [
                {"option_id": "A", "text": "原告甲"},
                {"option_id": "B", "text": "被告乙"},
                {"option_id": "C", "text": "法院"},
                {"option_id": "D", "text": "无法判断"},
            ],
            "correct_option": "A",
            "distractor_rationales": {"B": "主体错误", "C": "主体错误", "D": "材料足以判断"},
            "sample_tags": ["distractor"],
            "reference_answer": "原告甲",
            "rubric": {"required_points": ["原告甲"]},
            "source_evidence": [{"source_quote": "原告甲提交送货单。"}],
            "generator_hidden_thought": "不得发送给 Reviewer 的隐藏内容",
        }

    def test_validation_requires_explicit_reviewer_configuration(self):
        """验证启用 LLM 审题时缺少 Reviewer 配置会明确失败。"""
        validation = importlib.import_module("methodology.02_构建题集.legal.validation.validate")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            questions = root / "questions.jsonl"
            cases = root / "cases.jsonl"
            output = root / "validation.jsonl"
            questions.write_text(json.dumps(self._question(), ensure_ascii=False) + "\n", encoding="utf-8")
            cases.write_text("", encoding="utf-8")
            with patch.object(validation.llm_client, "load_env"), \
                 patch.object(validation.llm_client, "read_role", return_value=("https://generator.example", "gen-key", "gen-model")), \
                 patch.dict(os.environ, {"REVIEWER_BASE_URL": "", "REVIEWER_API_KEY": "", "REVIEWER_MODEL": ""}, clear=False):
                with self.assertRaisesRegex(ValueError, "显式角色配置"):
                    validation.run(questions, cases, output, use_llm=True, generator_base_url="https://generator.example", generator_model="gen-model")

    def test_validation_uses_independent_reviewer_and_whitelist(self):
        """验证 Reviewer 使用独立身份、白名单输入，并且 metadata 不含密钥。"""
        validation = importlib.import_module("methodology.02_构建题集.legal.validation.validate")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            questions = root / "questions.jsonl"
            cases = root / "cases.jsonl"
            output = root / "validation.jsonl"
            questions.write_text(json.dumps(self._question(), ensure_ascii=False) + "\n", encoding="utf-8")
            cases.write_text(json.dumps({
                "case_id": "case-reviewer",
                "external_text": "原告甲提交送货单。",
            }, ensure_ascii=False) + "\n", encoding="utf-8")
            rendered = []
            with patch.object(validation.llm_client, "load_env"), \
                 patch.object(validation.llm_client, "read_explicit_role", return_value=("https://reviewer.example", "review-key", "review-model")), \
                 patch.object(validation.llm_client, "build_client", return_value=object()), \
                 patch.object(validation, "load_template", return_value="template"), \
                 patch.object(validation, "render", side_effect=lambda template, values: rendered.append(values["item"]) or values["item"]), \
                 patch.object(validation.llm_client, "call_model", return_value=(json.dumps({"pass": True, "issues": []}), 0, 0, "stop")):
                findings = validation.run(questions, cases, output, use_llm=True, generator_base_url="https://generator.example", generator_model="gen-model")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["status"], "pass")
            self.assertEqual(len(rendered), 1)
            reviewer_input = json.loads(rendered[0])
            self.assertNotIn("generator_hidden_thought", reviewer_input)
            self.assertIn("reference_answer", reviewer_input)
            metadata = json.loads(Path(str(output) + ".metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["reviewer_model"], "review-model")
            self.assertTrue(metadata["reviewer_is_independent"])
            self.assertNotIn("review-key", json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()











