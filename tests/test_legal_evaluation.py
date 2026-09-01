"""法律阶段 03：模型作答契约测试。"""

import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.data_io import read_jsonl, write_jsonl

_evaluation_module = importlib.import_module("methodology.03_模型作答.legal.evaluation.run")
_scoring_module = importlib.import_module("methodology.04_结果评测.legal.scoring.run")
generate_answers = _evaluation_module.generate_answers
run = _evaluation_module.run
build_report = _scoring_module.build_report


class LegalEvaluationTests(unittest.TestCase):
    """保护 03 只生成原始回答，不提前执行评分。"""

    def setUp(self):
        """准备一条包含 rubric_judge 的正式题，验证作答阶段不会触发裁判。"""
        self.question = {
            "question_id": "legal_case_1_01",
            "case_id": "case_1",
            "split": "dev",
            "task_type": "争议焦点识别与规则适用",
            "scoring_method": "rubric_judge",
            "difficulty": "medium",
            "question": "【必要案情】卢某负有支付货款责任。\n\n【问题】谁应支付货款？",
            "reference_answer": "卢某应支付货款。",
            "rubric": {"required_points": ["卢某"], "bonus_points": [], "penalties": []},
        }

    @patch.object(_evaluation_module.llm_client, "call_model")
    def test_generate_answers_never_calls_judge_and_keeps_raw_record(self, call_model):
        """验证 03 对 rubric_judge 题也只调用被测模型并保存原始回答。"""
        call_model.return_value = ("卢某应支付货款。", 0.25, 42, "stop")
        rows, errors = generate_answers([self.question], object(), "contestant")
        self.assertEqual(errors, [])
        self.assertEqual(call_model.call_count, 1)
        self.assertEqual(call_model.call_args.args[2], self.question["question"])
        self.assertNotIn("required_points", call_model.call_args.args[2])
        self.assertEqual(rows[0]["model_answer"], "卢某应支付货款。")
        self.assertEqual(rows[0]["latency_seconds"], 0.25)
        self.assertEqual(rows[0]["total_tokens"], 42)
        self.assertNotIn("verdict", rows[0])
        self.assertNotIn("scoring_details", rows[0])
        self.assertFalse(hasattr(_evaluation_module, "legal_scorer"))

    @patch.object(_evaluation_module.llm_client, "call_model")
    def test_generate_answers_routes_context_types_and_preserves_dimension_metadata(self, call_model):
        """验证新题契约按 context_type 组织被测模型输入，并保留维度元数据。"""
        context_types = ["self_contained", "source_excerpt", "full_document", "scenario"]
        questions = [
            {
                **self.question,
                "question_id": f"q-{context_type}",
                "dimension_id": f"dimension-{context_type}",
                "task_type": f"任务-{context_type}",
                "context_type": context_type,
                "context": f"材料-{context_type}",
                "question": f"问题-{context_type}",
            }
            for context_type in context_types
        ]
        call_model.side_effect = [
            (f"回答-{context_type}", 0.1, 10, "stop")
            for context_type in context_types
        ]

        rows, errors = generate_answers(questions, object(), "contestant")

        self.assertEqual(errors, [])
        self.assertEqual(call_model.call_count, len(context_types))
        expected_labels = {
            "self_contained": "【必要背景】",
            "source_excerpt": "【原文材料】",
            "full_document": "【完整案件材料】",
            "scenario": "【风险场景】",
        }
        for question, call in zip(questions, call_model.call_args_list):
            prompt = call.args[2]
            self.assertIn(expected_labels[question["context_type"]], prompt)
            self.assertIn(question["context"], prompt)
            self.assertIn(question["question"], prompt)
            self.assertNotIn(question["reference_answer"], prompt)
        self.assertEqual(
            [
                (row["dimension_id"], row["task_type"], row["context_type"])
                for row in rows
            ],
            [
                (question["dimension_id"], question["task_type"], question["context_type"])
                for question in questions
            ],
        )

    def test_build_model_input_scans_complete_prompt_including_options_and_requirements(self):
        """验证包含选项和要求的完整外发 Prompt 必须经过 PII 扫描。"""
        question = {
            **self.question,
            "context_type": "self_contained",
            "context": "原告甲与被告乙签订合同。",
            "question": "请判断责任。",
            "question_format": "single_choice",
            "options": [
                {"option_id": "A", "text": "身份证号：110101199001011234"},
            ],
        }
        with self.assertRaisesRegex(ValueError, "身份证号"):
            _evaluation_module.build_model_input(question)

    def test_legacy_question_without_context_still_sends_public_options_and_requirements(self):
        """验证旧题无 context 时仍发送选项和公开作答要求，并扫描完整 Prompt。"""
        question = {
            **self.question,
            "question": "请判断责任。",
            "question_format": "single_choice",
            "options": [
                {"option_id": "A", "text": "原告承担责任"},
                {"option_id": "B", "text": "被告承担责任"},
            ],
            "answer_requirements": {
                "must_include_conclusion": True,
                "output_format": "只输出选项字母",
                "error_targets": ["不应外发"],
            },
        }
        prompt = _evaluation_module.build_model_input(question)
        self.assertIn("A. 原告承担责任", prompt)
        self.assertIn("B. 被告承担责任", prompt)
        self.assertIn("must_include_conclusion", prompt)
        self.assertNotIn("error_targets", prompt)

    def test_build_model_input_never_uses_full_text_or_scoring_fields(self):
        """验证外发 Prompt 不包含本地原文或评分字段。"""
        question = {
            **self.question,
            "context_type": "self_contained",
            "context": "必要背景材料。",
            "question": "请判断责任。",
            "question_format": "single_choice",
            "full_text": "本地原始全文：不应外发",
            "source_evidence": [{"source_quote": "不应外发的原文证据"}],
            "error_targets": ["statute_hallucination"],
        }
        prompt = _evaluation_module.build_model_input(question)
        self.assertIn("必要背景材料", prompt)
        self.assertNotIn("本地原始全文", prompt)
        self.assertNotIn("不应外发的原文证据", prompt)
        self.assertNotIn("statute_hallucination", prompt)

    @patch.object(_evaluation_module.llm_client, "build_client", return_value=object())
    @patch.object(_evaluation_module.llm_client, "read_role", return_value=("base", "key", "contestant"))
    @patch.object(_evaluation_module.llm_client, "load_env")
    @patch.object(_evaluation_module.llm_client, "call_model", return_value=("卢某应支付货款。", 0.1, 8, "stop"))
    def test_run_writes_only_raw_answer_artifacts(self, call_model, load_env, read_role, build_client):
        """验证 03 运行目录只有原始回答、调用错误和元数据。"""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_path = root / "questions.jsonl"
            output_dir = root / "answer-run"
            write_jsonl(input_path, [self.question])
            rows, actual_dir = run(input_path, output_dir, max_items=1)
            self.assertEqual(actual_dir, output_dir)
            self.assertEqual(len(rows), 1)
            self.assertTrue((output_dir / "legal_model_outputs.jsonl").is_file())
            self.assertTrue((output_dir / "legal_model_errors.jsonl").is_file())
            self.assertTrue((output_dir / "run_metadata.json").is_file())
            self.assertFalse((output_dir / "legal_evaluation_results.jsonl").exists())
            metadata = json.loads((output_dir / "run_metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["track"], "legal_benchmark.model_answering")
            self.assertEqual(read_jsonl(output_dir / "legal_model_outputs.jsonl")[0]["case_id"], "case_1")
            read_role.assert_called_once_with("CONTESTANT_A", "deepseek-v4-flash")

    def test_report_groups_by_split_and_task_type(self):
        """验证 04 报告仍按 split 和 task_type 汇总 verdict。"""
        report = build_report([
            {"question_id": "q1", "split": "dev", "task_type": "事实抽取", "scoring_method": "rule", "verdict": "PASS"},
            {"question_id": "q2", "split": "test", "task_type": "法律论证", "scoring_method": "rubric_judge", "verdict": "REVIEW"},
        ])
        self.assertIn("dev", report)
        self.assertIn("事实抽取", report)
        self.assertIn("PASS 1", report)


if __name__ == "__main__":
    unittest.main()
