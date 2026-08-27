"""法律评测执行测试。

被测模块：evaluation.run。覆盖逐题模型元数据、按 split/task_type 报告和法律结果目录隔离。
模型与客户端构建均使用 mock，文件测试使用 TemporaryDirectory，不调用真实 API。
失败表示正式题 schema、报告分组或结果写入边界发生回归。"""

import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.data_io import read_jsonl, write_jsonl

_evaluation_module = importlib.import_module("methodology.04_跑项目.legal.evaluation.run")
build_report = _evaluation_module.build_report
evaluate_questions = _evaluation_module.evaluate_questions
run = _evaluation_module.run


class LegalEvaluationTests(unittest.TestCase):
    def setUp(self):
        """测试目标：测试运行环境隔离。
准备数据：创建本测试类需要的临时目录、样例输入和 mock 对象。
调用函数：调用 unittest 的 setUp 初始化逻辑。
预期结果：每个测试从独立环境开始。
该断言保护的行为：保护测试之间不共享临时文件，也不污染正式结果目录。
副作用：只使用 mock、AST 或临时数据，不调用真实模型，不写入正式数据目录。"""

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

    @patch.object(_evaluation_module.llm_client, "call_model")
    def test_evaluate_questions_uses_new_schema_and_records_call_metadata(self, call_model):
        """测试目标：验证法律逐题结果使用新 schema 并记录模型调用元数据。
        准备数据：准备一条正式题，mock 被测模型回答和延迟/token。
        调用函数：调用 evaluate_questions。
        预期结果：结果含 question_id、case_id、model_answer、verdict、latency 和 total_tokens。
        该断言保护的行为：评测产物可追踪模型调用且不回退旧字段。"""

        call_model.return_value = ("卢某应支付货款。", 0.25, 42, "stop")
        rows, errors = evaluate_questions([self.question], object(), "contestant", None, None)
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["question_id"], "legal_case_1_01")
        self.assertEqual(rows[0]["verdict"], "PASS")
        self.assertEqual(rows[0]["latency_seconds"], 0.25)
        self.assertEqual(rows[0]["total_tokens"], 42)

    def test_report_groups_by_split_and_task_type(self):
        """测试目标：验证 Markdown 报告按 split 和 task_type 汇总 verdict。
        准备数据：准备不同 split、任务类型和 verdict 的结果行。
        调用函数：调用 build_report。
        预期结果：报告文本出现对应分组名称和计数。
        该断言保护的行为：项目报告能比较开发集、校准集、测试集及任务能力。"""

        report = build_report([
            {"question_id": "q1", "split": "dev", "task_type": "事实抽取", "scoring_method": "rule", "verdict": "PASS"},
            {"question_id": "q2", "split": "test", "task_type": "法律论证", "scoring_method": "rubric_judge", "verdict": "REVIEW"},
        ])
        self.assertIn("dev", report)
        self.assertIn("事实抽取", report)
        self.assertIn("PASS 1", report)

    @patch.object(_evaluation_module.llm_client, "build_client", return_value=object())
    @patch.object(_evaluation_module.llm_client, "read_role", return_value=("base", "key", "contestant"))
    @patch.object(_evaluation_module.llm_client, "load_env")
    @patch.object(_evaluation_module.llm_client, "call_model", return_value=("卢某应支付货款。", 0.1, 8, "stop"))
    def test_run_writes_only_to_requested_legal_output(self, call_model, load_env, read_role, build_client):
        """测试目标：验证法律 run 只写指定法律输出目录。
        准备数据：用临时题集和输出目录，mock 客户端构建与模型调用。
        调用函数：调用 evaluation.run。
        预期结果：目标目录出现法律结果、错误、报告和元数据，返回路径正确。
        该断言保护的行为：第三条评测线不会污染 C-Eval 或 Pairwise 结果目录。"""

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_path = root / "questions.jsonl"
            output_dir = root / "legal-results"
            write_jsonl(input_path, [self.question])
            rows, actual_dir = run(input_path, output_dir, max_items=1)
            self.assertEqual(actual_dir, output_dir)
            self.assertEqual(len(rows), 1)
            self.assertTrue((output_dir / "legal_evaluation_results.jsonl").is_file())
            self.assertTrue((output_dir / "legal_evaluation_report.md").is_file())
            self.assertTrue((output_dir / "run_metadata.json").is_file())
            metadata = json.loads((output_dir / "run_metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["track"], "legal_benchmark.evaluation")
            self.assertEqual(read_jsonl(output_dir / "legal_evaluation_results.jsonl")[0]["case_id"], "case_1")


if __name__ == "__main__":
    unittest.main()
