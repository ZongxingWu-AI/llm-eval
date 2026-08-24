"""测试模块：tests/test_legal_evaluation.py。

本文件验证项目中的一个具体行为或模块边界。测试输入通常是内存中的最小样例，测试输出是断言结果，不调用真实模型 API。

项目位置：tests/test_legal_evaluation.py。
主要用途：项目测试模块，验证公共基础层和三条评测线的行为、数据隔离与文档规范。
输入：输入来自测试夹具、临时目录和项目模块。
输出：输出为测试断言结果，不产生正式评测数据。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：通常只创建临时文件或调用测试替身，不调用真实模型 API。
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.data_io import read_jsonl, write_jsonl
from tracks.legal_benchmark.evaluation.run import build_report, evaluate_questions, run

from tracks.legal_benchmark.evaluation.run import build_report, evaluate_questions, run


class LegalEvaluationTests(unittest.TestCase):
    def setUp(self):
        """为当前测试准备独立的临时目录、样例数据或 mock 环境。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        self.question = {
            "question_id": "legal_case_1_01",
            "case_id": "case_1",
            "split": "dev",
            "primary_issue": "付款责任",
            "task_type": "争议焦点识别与规则适用",
            "reasoning_capabilities": ["事实抽取", "法律规则适用"],
            "answer_type": "结构化论述",
            "scoring_method": "rule",
            "difficulty": "medium",
            "question": "谁应支付货款？",
            "reference_answer": "卢某应支付货款。",
            "rubric": {"required_points": ["卢某", "货款"], "bonus_points": [], "penalties": []},
            "source_evidence": [{"source_section": "judgment", "source_quote": "卢某支付货款"}],
        }

    @patch("tracks.legal_benchmark.evaluation.run.llm_client.call_model")
    def test_evaluate_questions_uses_new_schema_and_records_call_metadata(self, call_model):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self、call_model。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        call_model.return_value = ("卢某应支付货款。", 0.25, 42, "stop")
        rows, errors = evaluate_questions([self.question], object(), "contestant", None, None)
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["question_id"], "legal_case_1_01")
        self.assertEqual(rows[0]["verdict"], "PASS")
        self.assertEqual(rows[0]["latency_seconds"], 0.25)
        self.assertEqual(rows[0]["total_tokens"], 42)

    def test_report_groups_by_split_and_task_type(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        report = build_report([
            {"question_id": "q1", "split": "dev", "task_type": "事实抽取", "scoring_method": "rule", "verdict": "PASS"},
            {"question_id": "q2", "split": "test", "task_type": "法律论证", "scoring_method": "rubric_judge", "verdict": "REVIEW"},
        ])
        self.assertIn("dev", report)
        self.assertIn("事实抽取", report)
        self.assertIn("PASS 1", report)

    @patch("tracks.legal_benchmark.evaluation.run.llm_client.build_client", return_value=object())
    @patch("tracks.legal_benchmark.evaluation.run.llm_client.read_role", return_value=("base", "key", "contestant"))
    @patch("tracks.legal_benchmark.evaluation.run.llm_client.load_env")
    @patch("tracks.legal_benchmark.evaluation.run.llm_client.call_model", return_value=("卢某应支付货款。", 0.1, 8, "stop"))
    def test_run_writes_only_to_requested_legal_output(self, call_model, load_env, read_role, build_client):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self、call_model、load_env、read_role、build_client。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_path = root / "questions.jsonl"
            output_dir = root / "legal-results"
            write_jsonl(input_path, [self.question])
            rows, actual_dir = run(input_path, output_dir, max_items=1)
            self.assertEqual(actual_dir, output_dir)
            self.assertEqual(len(rows), 1)
            self.assertTrue((output_dir / "legal_results.jsonl").is_file())
            self.assertTrue((output_dir / "legal_report.md").is_file())
            self.assertTrue((output_dir / "run_metadata.json").is_file())
            metadata = json.loads((output_dir / "run_metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["track"], "legal_benchmark.evaluation")
            self.assertEqual(read_jsonl(output_dir / "legal_results.jsonl")[0]["case_id"], "case_1")


if __name__ == "__main__":
    unittest.main()
