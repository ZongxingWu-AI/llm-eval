"""法律正式题集验证测试。

被测模块：validation.check_row 和 validate。覆盖 source quote 章节定位及同案问题不得跨 split。
使用内存题目和案件，不写报告、不调用模型。
失败表示不可追溯引用或数据泄漏可能未被发布前检查发现。"""

import importlib
import json
import tempfile
import unittest
from pathlib import Path

from core.data_io import read_jsonl, write_jsonl

_validation = importlib.import_module("methodology.02_构建题集.legal.validation.validate")
check_row = _validation.check_row
validate = _validation.validate
run = _validation.run

class LegalValidationTests(unittest.TestCase):

    def setUp(self):
        """测试目标：测试运行环境隔离。
准备数据：创建本测试类需要的临时目录、样例输入和 mock 对象。
调用函数：调用 unittest 的 setUp 初始化逻辑。
预期结果：每个测试从独立环境开始。
该断言保护的行为：保护测试之间不共享临时文件，也不污染正式结果目录。
副作用：只使用 mock、AST 或临时数据，不调用真实模型，不写入正式数据目录。"""

        self.row = {
            "question_id": "q1", "case_id": "case_1", "split": "dev",
            "primary_issue": "付款责任", "task_type": "事实抽取",
            "reasoning_capabilities": ["事实抽取"], "answer_type": "短答案",
            "scoring_method": "rule", "difficulty": "easy", "risk_level": "low",
            "question": "谁付款？", "reference_answer": "卢某付款。",
            "rubric": {"required_points": ["卢某"]},
            "source_evidence": [{"source_section": "judgment", "source_quote": "卢某支付货款"}],
            "case_classification": {
                "domain": "民事", "procedure_stage": "一审", "document_type": "判决书",
                "primary_category": "合同、准合同纠纷",
                "cause_path": ["合同、准合同纠纷", "买卖合同纠纷"],
                "procedure_tags": [], "evidence_tags": ["书证"],
            },
        }
        self.case = {"case_id": "case_1", "sections": {"judgment": "判决如下：卢某支付货款。"}}

    def test_run_writes_validation_report_and_metadata(self):
        """测试目标：验证验证阶段写出 JSONL、Markdown 和相邻 metadata。
        准备数据：写入一条合法正式题和对应 extract 案件到临时目录。
        调用函数：调用 validation.run 并显式指定输入、案件和输出路径。
        预期结果：校验结果通过，报告与 metadata 记录真实运行信息。
        该断言保护的行为：验证阶段独立于具体批次，并保留运行级可追踪信息。
        """

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_path = root / "releases" / "legal_questions_release_v1.jsonl"
            cases_path = root / "extract" / "legal_cases_extract.jsonl"
            output_path = root / "validation" / "legal_questions_validation_v1.jsonl"
            write_jsonl(input_path, [self.row])
            write_jsonl(cases_path, [self.case])

            findings = run(input_path, cases_path, output_path)

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["status"], "pass")
            self.assertEqual(read_jsonl(output_path)[0]["status"], "pass")
            self.assertTrue(output_path.with_suffix(".md").is_file())
            metadata_path = output_path.with_suffix(output_path.suffix + ".metadata.json")
            self.assertTrue(metadata_path.is_file())
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["track"], "legal_benchmark.validation")
            self.assertEqual(metadata["questions"], 1)
            self.assertEqual(metadata["failures"], 0)

    def test_source_quote_must_exist_in_named_section(self):
        """测试目标：验证证据短引必须出现在声明的案件章节中。
        准备数据：准备一题引用不存在文本和一个含 sections 的案件。
        调用函数：调用 check_row。
        预期结果：issues 包含 source_quote 无法定位。
        该断言保护的行为：模型编造或章节标错的证据不能通过正式校验。"""

        self.assertEqual(check_row(self.row, self.case), [])
        bad = {**self.row, "source_evidence": [{"source_section": "judgment", "source_quote": "任某支付货款"}]}
        self.assertTrue(any("无法" in issue for issue in check_row(bad, self.case)))

    def test_same_case_cannot_cross_splits(self):
        """测试目标：验证同一 case_id 出现在多个 split 时整组报告错误。
        准备数据：准备同案两题分别标为 dev 和 test。
        调用函数：调用 validate。
        预期结果：相关验证记录均为无效并包含跨 split 问题。
        该断言保护的行为：同案事实不会泄漏到最终测试集。"""

        second = {**self.row, "question_id": "q2", "question": "第二题", "split": "test"}
        findings = validate([self.row, second], [self.case])
        self.assertTrue(any("同案跨 split" in issue for finding in findings for issue in finding["issues"]))


if __name__ == "__main__":
    unittest.main()
