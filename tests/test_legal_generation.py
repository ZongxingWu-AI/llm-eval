"""法律候选题生成测试。

被测模块：generation.generate。覆盖候选题生成的 JSONL 读写、模型调用路由、来源证据过滤和 pending 状态。
模型调用使用 mock，不访问真实 API。
失败表示生成阶段无法从 cleaned 案件稳定写出 drafts，导致后续题集构建无法启动。
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


class LegalGenerationTests(unittest.TestCase):
    def _case(self):
        """测试目标：生成阶段最小案件夹具。
        准备数据：提供带章节文本、案件分类和案件 ID 的 cleaned 案件。
        调用函数：由 run 读取并传入候选题生成逻辑。
        预期结果：模型生成的 source_evidence 可以回查到指定章节。
        该断言保护的行为：候选题必须保留案件来源定位，不能脱离原文生成。
        副作用：只返回内存字典，不访问正式数据目录或模型服务。"""

        return {
            "case_id": "case_generation_1",
            "sections": {
                "court_reasoning": "法院认定卢某应支付货款。",
                "judgment": "判决卢某支付货款。",
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
            output_path = root / "drafts" / "candidate_questions.jsonl"
            write_jsonl(input_path, [self._case()])

            rows = run(input_path, output_path, max_items=1, questions_per_case=2)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["review_status"], "pending")
            self.assertEqual(rows[0]["case_id"], "case_generation_1")
            self.assertEqual(read_jsonl(output_path)[0]["question"], "谁应支付货款？")
            errors = read_jsonl(output_path.with_suffix(".errors.jsonl"))
            self.assertEqual(len(errors), 1)
            self.assertTrue((output_path.with_suffix(output_path.suffix + ".metadata.json")).is_file())


if __name__ == "__main__":
    unittest.main()
