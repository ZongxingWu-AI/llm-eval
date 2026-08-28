"""法律候选题生成测试。

被测模块：generation.generate。覆盖候选题生成的 JSONL 读写、模型调用路由、来源证据过滤和 pending 状态。
模型调用使用 mock，不访问真实 API。
失败表示生成阶段无法从 extract 案件稳定写出 drafts，导致后续题集构建无法启动。
"""

import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.data_io import read_jsonl, write_jsonl

_generation_module = importlib.import_module("methodology.02_构建题集.legal.generation.generate")
run = _generation_module.run
build_generation_input = _generation_module._build_generation_input
valid_evidence = _generation_module._valid_evidence
load_dimension_catalog = _generation_module.load_dimension_catalog
generate_for_dimension = _generation_module.generate_for_dimension


class LegalGenerationTests(unittest.TestCase):
    def _catalog(self, root: Path) -> Path:
        """执行法律评测测试。"""
        path = root / "dimension_catalog.json"
        path.write_text(json.dumps({"dimensions": [
            {"dimension_id": "fact_extraction", "task_type": "事实抽取", "reasoning_capabilities": ["事实抽取"], "context_types": ["source_excerpt", "full_document"], "default_context_type": "source_excerpt", "recommended_scoring_method": "rule", "prompt_template": "fact_extraction.md"},
            {"dimension_id": "rule_application", "task_type": "争议焦点识别与规则适用", "reasoning_capabilities": ["法律规则适用"], "context_types": ["self_contained"], "default_context_type": "self_contained", "recommended_scoring_method": "rubric_judge", "prompt_template": "rule_application.md"}
        ]}, ensure_ascii=False), encoding="utf-8")
        return path

    def _case(self):
        """测试目标：生成阶段最小案件夹具。
        准备数据：提供带章节文本、案件分类和案件 ID 的 extract 案件。
        调用函数：由 run 读取并传入候选题生成逻辑。
        预期结果：模型生成的 source_evidence 可以回查到指定章节。
        该断言保护的行为：候选题必须保留案件来源定位，不能脱离原文生成。
        副作用：只返回内存字典，不访问正式数据目录或模型服务。"""

        return {
            "case_id": "case_generation_1",
            "full_text": "法院认定卢某应支付货款。判决卢某支付货款。",
            "sections": {
                "court_reasoning": "法院认定卢某应支付货款。",
                "judgment": "判决卢某支付货款。",
            },
            "facts_summary": "卢某负有支付货款的责任。",
            "legal_extraction": {
                "legal_issues": ["付款责任"],
                "evidence_findings": [],
                "conclusions": [{
                    "conclusion": "卢某应支付货款。",
                    "source_section": "judgment",
                    "source_quote": "判决卢某支付货款。",
                }],
            },
            "classification": {
                "domain": "民事",
                "procedure_stage": "一审",
                "document_type": "判决书",
                "primary_category": "合同、准合同纠纷",
                "cause_path": ["合同、准合同纠纷", "买卖合同纠纷"],
                "procedure_tags": [],
                "evidence_tags": ["书证"],
            },
        }

    @patch.object(_generation_module, "llm_client", create=True)
    def test_run_writes_pending_candidates_and_filters_invalid_evidence(self, llm_client):
        """测试目标：验证生成阶段写出候选题、错误记录和运行元数据。
        准备数据：mock 配置读取与模型返回一条合法题和一条无效来源题。
        调用函数：调用 generation.run，并指定临时输入输出路径。
        预期结果：合法题写入 drafts 且状态为 pending，无效来源题进入 errors。
        该断言保护的行为：只有能回查原文的题目才能进入候选题文件，且批处理不因单题失败中断。
        副作用：只写临时目录，不调用真实 API。
        """

        candidate = {
            "primary_issue": "付款责任",
            "task_type": "事实抽取",
            "reasoning_capabilities": ["事实抽取"],
            "answer_type": "短答案",
            "scoring_method": "rule",
            "difficulty": "easy",
            "risk_level": "low",
            "context_type": "source_excerpt",
            "context": "卢某负有支付货款责任。",
            "question": "谁应支付货款？",
            "reference_answer": "卢某应支付货款。",
            "rubric": {"required_points": ["卢某"], "bonus_points": [], "penalties": []},
            "source_evidence": [{"source_section": "judgment", "source_quote": "判决卢某支付货款。"}],
        }
        invalid = dict(candidate)
        invalid["question"] = "无效来源题"
        invalid["source_evidence"] = [{"source_section": "judgment", "source_quote": "不存在的引用"}]
        llm_client.load_env.return_value = None
        llm_client.read_role.return_value = ("base", "key", "generator")
        llm_client.build_client.return_value = object()
        llm_client.call_model.return_value = (json.dumps([candidate, invalid], ensure_ascii=False), 0.1, 12, "stop")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "cases.jsonl"
            output_path = root / "drafts" / "legal_questions_draft.jsonl"
            write_jsonl(input_path, [self._case()])

            rows = run(input_path, output_path, max_items=1, questions_per_case=2)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["review_status"], "pending")
            self.assertEqual(rows[0]["case_id"], "case_generation_1")
            self.assertEqual(read_jsonl(output_path)[0]["question"], "谁应支付货款？")
            errors = read_jsonl(output_path.with_suffix(".errors.jsonl"))
            self.assertEqual(len(errors), 1)
            self.assertTrue((output_path.with_suffix(output_path.suffix + ".metadata.json")).is_file())
            prompt = llm_client.call_model.call_args.args[2]
            self.assertIn('"source_material"', prompt)
            self.assertIn("判决卢某支付货款。", prompt)
            self.assertIn("完整案件与章节", prompt)
            self.assertIn("维度配置", prompt)
            self.assertIn('"full_text"', prompt)
            self.assertIn('"sections"', prompt)
            self.assertIn("context", prompt)
            self.assertIn("question", prompt)

    def test_generation_input_keeps_full_document_and_fact_map(self):
        """执行法律评测测试。"""
        case = self._case()
        case["legal_extraction"]["evidence_findings"] = [{
            "conclusion": "法院认定卢某应支付货款。",
            "source_section": "court_reasoning",
            "source_quote": "法院认定卢某应支付货款。",
        }]
        case["legal_extraction"]["conclusions"].append({
            "conclusion": "重复引用",
            "source_section": "court_reasoning",
            "source_quote": "法院认定卢某应支付货款。",
        })
        case["legal_extraction"]["conclusions"].append({
            "conclusion": "不存在的引用",
            "source_section": "judgment",
            "source_quote": "不存在的引用",
        })

        result = build_generation_input(case)

        self.assertEqual(result["full_text"], case["full_text"])
        self.assertEqual(result["sections"], case["sections"])
        self.assertEqual(len(result["source_material"]), 2)
        self.assertTrue(all(item["source_quote"] in item["context"] for item in result["source_material"]))

    def test_load_dimension_catalog_indexes_unique_dimensions(self):
        """执行法律评测测试。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog = load_dimension_catalog(self._catalog(Path(temp_dir)))
        self.assertEqual(set(catalog), {"fact_extraction", "rule_application"})
        self.assertEqual(catalog["rule_application"]["task_type"], "争议焦点识别与规则适用")

    @patch.object(_generation_module.llm_client, "call_model")
    def test_generation_rejects_missing_independent_context(self, call_model):
        """验证出题模型未返回独立 context 时只记录该题错误。"""
        candidate = {
            "primary_issue": "付款责任", "task_type": "事实抽取",
            "reasoning_capabilities": ["事实抽取"], "answer_type": "短答案",
            "scoring_method": "rule", "difficulty": "easy", "risk_level": "low",
            "question": "谁应支付货款？", "reference_answer": "卢某应支付货款。",
            "rubric": {"required_points": ["卢某"], "bonus_points": [], "penalties": []},
            "source_evidence": [{"source_section": "judgment", "source_quote": "判决卢某支付货款。"}],
        }
        call_model.return_value = (json.dumps([candidate], ensure_ascii=False), 0, 0, "stop")
        with tempfile.TemporaryDirectory() as temp_dir:
            results, errors = generate_for_dimension(
                self._case(), object(), "model", "fact_extraction", 1,
                catalog_path=self._catalog(Path(temp_dir)),
            )
        self.assertEqual(results, [])
        self.assertTrue(any("context" in error for error in errors), errors)

    @patch.object(_generation_module.llm_client, "call_model")
    def test_generate_for_dimension_routes_prompt_and_adds_new_contract(self, call_model):
        """执行法律评测测试。"""
        candidate = {"primary_issue": "付款责任", "task_type": "争议焦点识别与规则适用", "reasoning_capabilities": ["法律规则适用"], "answer_type": "长答案", "scoring_method": "rubric_judge", "difficulty": "medium", "risk_level": "medium", "dimension_id": "rule_application", "context_type": "self_contained", "context": "甲已交货，乙尚未支付货款。", "question": "乙是否应承担付款责任？请说明理由。", "reference_answer": "乙应依约支付货款。", "rubric": {"required_points": ["付款义务"], "bonus_points": [], "penalties": []}, "source_evidence": [{"source_section": "judgment", "source_quote": "判决卢某支付货款。"}]}
        call_model.return_value = (json.dumps([candidate], ensure_ascii=False), 0, 0, "stop")
        with tempfile.TemporaryDirectory() as temp_dir:
            results, errors = generate_for_dimension(self._case(), object(), "model", "rule_application", 1, catalog_path=self._catalog(Path(temp_dir)))
        self.assertEqual(errors, [])
        self.assertEqual(results[0]["dimension_id"], "rule_application")
        self.assertEqual(results[0]["context_type"], "self_contained")
        self.assertEqual(results[0]["context"], "甲已交货，乙尚未支付货款。")
        prompt = call_model.call_args.args[2]
        self.assertIn("法律规则适用维度", prompt)
        self.assertIn('"full_text"', prompt)
        self.assertIn("法院认定卢某应支付货款。", prompt)

    def test_invalid_dimension_has_explicit_error(self):
        """执行法律评测测试。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "未知法律评测维度"):
                generate_for_dimension(self._case(), object(), "model", "not_a_dimension", 1, catalog_path=self._catalog(Path(temp_dir)))

    @patch.object(_generation_module.llm_client, "call_model")
    def test_dimension_generation_failure_does_not_drop_other_dimension(self, call_model):
        """执行法律评测测试。"""
        valid = {"primary_issue": "付款事实", "task_type": "事实抽取", "reasoning_capabilities": ["事实抽取"], "answer_type": "短答案", "scoring_method": "rule", "difficulty": "easy", "risk_level": "low", "dimension_id": "fact_extraction", "context_type": "source_excerpt", "context": "判决卢某支付货款。", "question": "谁承担付款义务？", "reference_answer": "卢某。", "rubric": {"required_points": ["卢某"], "bonus_points": [], "penalties": []}, "source_evidence": [{"source_section": "judgment", "source_quote": "判决卢某支付货款。"}]}
        call_model.side_effect = [RuntimeError("规则适用生成失败"), (json.dumps([valid], ensure_ascii=False), 0, 0, "stop")]
        with tempfile.TemporaryDirectory() as temp_dir:
            results, errors = _generation_module.generate_dimension_requests(self._case(), object(), "model", {"rule_application": 1, "fact_extraction": 1}, catalog_path=self._catalog(Path(temp_dir)))
        self.assertEqual([row["dimension_id"] for row in results], ["fact_extraction"])
        self.assertEqual(len(errors), 1)
        self.assertIn("rule_application", errors[0])

    def test_valid_evidence_uses_full_text_and_repairs_wrong_section(self):
        """执行法律评测测试。"""
        case = self._case()
        evidence = [{
            "source_section": "judgment",
            "source_quote": "法院认定卢某应支付货款。",
        }]

        result = valid_evidence(case, evidence)

        self.assertEqual(result, [{
            "source_section": "court_reasoning",
            "source_quote": "法院认定卢某应支付货款。",
        }])


if __name__ == "__main__":
    unittest.main()
