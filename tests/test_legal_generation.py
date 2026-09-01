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
load_blueprint_requests = _generation_module.load_blueprint_requests


class LegalGenerationTests(unittest.TestCase):
    def _catalog(self, root: Path) -> Path:
        """执行法律评测测试。"""
        path = root / "dimension_catalog.json"
        path.write_text(json.dumps({"dimensions": [
            {"dimension_id": "fact_extraction", "task_type": "事实抽取", "context_types": ["source_excerpt", "full_document"], "default_context_type": "source_excerpt", "recommended_scoring_method": "rule", "prompt_template": "fact_extraction.md"},
            {"dimension_id": "rule_application", "task_type": "争议焦点识别与规则适用", "context_types": ["self_contained"], "default_context_type": "self_contained", "recommended_scoring_method": "rubric_judge", "prompt_template": "rule_application.md"}
        ]}, ensure_ascii=False), encoding="utf-8")
        return path

    def _case(self):
        """测试目标：生成阶段最小案件夹具。
        准备数据：提供脱敏全文、案件分类和案件 ID 的 extract 案件。
        调用函数：由 run 读取并传入候选题生成逻辑。
        预期结果：模型生成的 source_evidence 可以回查到脱敏全文。
        该断言保护的行为：候选题必须保留案件来源定位，不能脱离原文生成。
        副作用：只返回内存字典，不访问正式数据目录或模型服务。"""

        return {
            "case_id": "case_generation_1",
            "external_text": "法院认定卢某应支付货款。判决卢某支付货款。",
            "quality": {"extraction": {
                "method": "llm_grounded",
                "status": "ready_for_generation",
                "review_status": "ready_for_generation",
                "errors": [],
            }},
            "legal_extraction": {"case_fact_map": {
                "key_facts": [{"text": "卢某应支付货款", "source_quote": "法院认定卢某应支付货款。"}],
                "party_relationships": [], "claims": [], "defenses": [], "disputed_issues": [],
                "evidence": [{"text": "法院认定卢某应支付货款", "source_quote": "法院认定卢某应支付货款。"}],
                "court_found_facts": [], "procedural_timeline": [], "applied_laws": [],
                "court_reasoning": [{"text": "法院认定卢某应支付货款", "source_quote": "法院认定卢某应支付货款。"}],
                "judgment_results": [{"text": "判决卢某支付货款", "source_quote": "判决卢某支付货款。"}],
            }},
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
            "task_type": "事实抽取",
            "answer_type": "短答案",
            "scoring_method": "rule",
            "difficulty": "easy",
            "risk_level": "low",
            "context_type": "source_excerpt",
            "context": "卢某负有支付货款责任。",
            "question": "谁应支付货款？",
            "reference_answer": "卢某应支付货款。",
            "rubric": {"required_points": ["卢某"], "bonus_points": [], "penalties": []},
            "source_evidence": [{"source_quote": "判决卢某支付货款。"}],
        }
        invalid = dict(candidate)
        invalid["question"] = "无效来源题"
        invalid["source_evidence"] = [{"source_quote": "不存在的引用"}]
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
            self.assertIn("脱敏全文", prompt)
            self.assertIn("维度配置", prompt)
            self.assertIn('"external_text"', prompt)
            self.assertNotIn('"external_sections"', prompt)
            self.assertNotIn('"full_text"', prompt)
            self.assertNotIn('"sections"', prompt)
            self.assertNotIn('"facts_summary"', prompt)
            self.assertIn("context", prompt)
            self.assertIn("question", prompt)

    def test_generation_input_keeps_full_document_and_fact_map(self):
        """执行法律评测测试。"""
        case = self._case()

        result = build_generation_input(case)

        self.assertEqual(result["external_text"], case["external_text"])
        self.assertNotIn("external_sections", result)
        self.assertNotIn("full_text", result)
        self.assertNotIn("sections", result)
        self.assertEqual(len(result["source_material"]), 2)
        self.assertTrue(all(item["source_quote"] in case["external_text"] for item in result["source_material"]))

    def test_prediction_rejects_quote_crossing_outcome_boundary(self):
        """预测题不能使用跨过明确裁判结果边界的长引用。"""
        text = "事实材料。判决如下：乙承担责任。"
        quote = "事实材料。判决如下："
        self.assertTrue(_generation_module._quote_is_outcome(text, quote))
    def test_generation_input_prediction_removes_court_fields_and_outcome_region(self):
        """预测题输入不应暴露法院结论字段、摘要或明确裁判结果区域。"""
        case = self._case()
        case["external_text"] = "法院认定卢某应支付货款。判决如下：判决卢某支付货款。"
        result = build_generation_input(case, dimension_id="judgment_prediction")

        self.assertNotIn("判决卢某支付货款。", result["external_text"])
        self.assertNotIn("court_found_facts", result["fact_map"])
        self.assertNotIn("court_reasoning", result["fact_map"])
        self.assertNotIn("judgment_results", result["fact_map"])
        self.assertNotIn("court_found_facts", result["legal_extraction"]["case_fact_map"])
        self.assertNotIn("court_reasoning", result["legal_extraction"]["case_fact_map"])
        self.assertNotIn("judgment_results", result["legal_extraction"]["case_fact_map"])
        self.assertNotIn("facts_summary", result)
        self.assertTrue(all("判决卢某支付货款。" not in item["source_quote"] for item in result["source_material"]))
        self.assertTrue(all(set(item) == {"fact_field", "source_quote", "source_quote_sha256"} for item in result["source_material"]))

    def test_generation_input_normalises_fact_entries_to_current_fields(self):
        """进入出题 Prompt 的事实地图只保留当前字段，并重新生成哈希。"""
        case = self._case()
        case["legal_extraction"]["case_fact_map"]["claims"] = [{
            "text": "甲主张付款",
            "extra_note": "不属于出题输入",
            "source_quote": "法院认定卢某应支付货款。",
            "source_quote_sha256": "待重新生成",
        }]
        result = build_generation_input(case)
        entry = result["fact_map"]["claims"][0]
        self.assertEqual(set(entry), {"text", "source_quote", "source_quote_sha256"})
        self.assertNotIn("extra_note", json.dumps(result, ensure_ascii=False))

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
            "task_type": "事实抽取",
            "answer_type": "短答案",
            "scoring_method": "rule", "difficulty": "easy", "risk_level": "low",
            "question": "谁应支付货款？", "reference_answer": "卢某应支付货款。",
            "rubric": {"required_points": ["卢某"], "bonus_points": [], "penalties": []},
            "source_evidence": [{"source_quote": "判决卢某支付货款。"}],
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
        candidate = {"task_type": "争议焦点识别与规则适用", "answer_type": "长答案", "scoring_method": "rubric_judge", "difficulty": "medium", "risk_level": "medium", "dimension_id": "rule_application", "context_type": "self_contained", "context": "甲已交货，乙尚未支付货款。", "question": "乙是否应承担付款责任？请说明理由。", "reference_answer": "乙应依约支付货款。", "rubric": {"required_points": ["付款义务"], "bonus_points": [], "penalties": []}, "source_evidence": [{"source_quote": "判决卢某支付货款。"}]}
        call_model.return_value = (json.dumps([candidate], ensure_ascii=False), 0, 0, "stop")
        with tempfile.TemporaryDirectory() as temp_dir:
            results, errors = generate_for_dimension(self._case(), object(), "model", "rule_application", 1, catalog_path=self._catalog(Path(temp_dir)))
        self.assertEqual(errors, [])
        self.assertEqual(results[0]["dimension_id"], "rule_application")
        self.assertEqual(results[0]["context_type"], "self_contained")
        self.assertEqual(results[0]["context"], "甲已交货，乙尚未支付货款。")
        prompt = call_model.call_args.args[2]
        self.assertIn("法律规则适用维度", prompt)
        self.assertIn('"external_text"', prompt)
        self.assertIn("法院认定卢某应支付货款。", prompt)
        self.assertNotIn('"full_text"', prompt)

    def test_invalid_dimension_has_explicit_error(self):
        """执行法律评测测试。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "未知法律评测维度"):
                generate_for_dimension(self._case(), object(), "model", "not_a_dimension", 1, catalog_path=self._catalog(Path(temp_dir)))

    @patch.object(_generation_module.llm_client, "call_model")
    def test_dimension_generation_failure_does_not_drop_other_dimension(self, call_model):
        """执行法律评测测试。"""
        valid = {"task_type": "事实抽取", "answer_type": "短答案", "scoring_method": "rule", "difficulty": "easy", "risk_level": "low", "dimension_id": "fact_extraction", "context_type": "source_excerpt", "context": "判决卢某支付货款。", "question": "谁承担付款义务？", "reference_answer": "卢某。", "rubric": {"required_points": ["卢某"], "bonus_points": [], "penalties": []}, "source_evidence": [{"source_quote": "判决卢某支付货款。"}]}
        call_model.side_effect = [RuntimeError("规则适用生成失败"), (json.dumps([valid], ensure_ascii=False), 0, 0, "stop")]
        with tempfile.TemporaryDirectory() as temp_dir:
            results, errors = _generation_module.generate_dimension_requests(self._case(), object(), "model", {"rule_application": 1, "fact_extraction": 1}, catalog_path=self._catalog(Path(temp_dir)))
        self.assertEqual([row["dimension_id"] for row in results], ["fact_extraction"])
        self.assertEqual(len(errors), 1)
        self.assertIn("rule_application", errors[0])

    def test_valid_evidence_uses_full_text_and_repairs_wrong_section(self):
        """执行法律评测测试。"""
        case = self._case()
        evidence = [{"source_quote": "法院认定卢某应支付货款。"}]

        result = valid_evidence(case, evidence)

        self.assertEqual(result[0]["source_quote"], "法院认定卢某应支付货款。")
        self.assertEqual(len(result[0]["source_quote_sha256"]), 64)

    def test_blueprint_requests_prefer_dimension_format_quotas(self):
        """交叉蓝图应展开为独立的维度×题型请求。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "blueprint.json"
            path.write_text(json.dumps({
                "blueprint_id": "test",
                "dimension_quotas": {"fact_extraction": 99},
                "dimension_format_quotas": {
                    "fact_extraction": {"single_choice": 2, "short_answer": 1},
                    "rule_application": {"case_analysis": 0},
                },
            }), encoding="utf-8")
            requests, document = load_blueprint_requests(path)
        self.assertEqual(requests, [
            ("fact_extraction", {"question_format": "single_choice", "count": 2}),
            ("fact_extraction", {"question_format": "short_answer", "count": 1}),
        ])
        self.assertEqual(document["blueprint_id"], "test")

    def test_blueprint_requests_fallback_to_dimension_quotas(self):
        """没有交叉配额时应兼容一级维度配额。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "blueprint.json"
            path.write_text(json.dumps({"dimension_quotas": {"fact_extraction": 2}}), encoding="utf-8")
            requests, _ = load_blueprint_requests(path)
        self.assertEqual(requests, [("fact_extraction", {"count": 2})])

    @patch.object(_generation_module, "generate_for_dimension")
    @patch.object(_generation_module.llm_client, "build_client")
    @patch.object(_generation_module.llm_client, "read_role")
    @patch.object(_generation_module.llm_client, "load_env")
    def test_run_blueprint_records_actual_dimension_format_counts(
        self, load_env, read_role, build_client, generate_for_dimension
    ):
        """蓝图入口应展开为请求级任务，并在 metadata 中记录实际统计。"""
        generate_for_dimension.return_value = ([{
            "question_id": "q1", "dimension_id": "fact_extraction",
            "question_format": "single_choice",
        }], [])
        read_role.return_value = ("base", "key", "model")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "cases.jsonl"
            output_path = root / "drafts.jsonl"
            input_path.write_text(json.dumps(self._case(), ensure_ascii=False) + "\n", encoding="utf-8")
            blueprint = root / "blueprint.json"
            blueprint.write_text(json.dumps({
                "blueprint_id": "test",
                "dimension_format_quotas": {"fact_extraction": {"single_choice": 2}},
            }), encoding="utf-8")
            rows = run(input_path, output_path, blueprint_path=blueprint)
            metadata = json.loads(Path(str(output_path) + ".metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 1)
        generate_for_dimension.assert_called_once()
        call_args = generate_for_dimension.call_args
        self.assertEqual(call_args.args[3:5], ("fact_extraction", 2))
        self.assertEqual(call_args.kwargs["question_format"], "single_choice")
        self.assertEqual(metadata["dimension_counts"], {"fact_extraction": 1})
        self.assertEqual(metadata["question_format_counts"], {"single_choice": 1})
        self.assertEqual(metadata["requested_dimension_format_counts"], {"fact_extraction": {"single_choice": 2}})



if __name__ == "__main__":
    unittest.main()

class GenerationConcurrencyTests(unittest.TestCase):
    def _case(self, case_id: str):
        """构造指定案件编号的并发测试案件。"""
        case = LegalGenerationTests()._case()
        case["case_id"] = case_id
        return case

    def _blueprint(self, root: Path) -> Path:
        """写入包含两个维度题型请求的并发测试蓝图。"""
        path = root / "blueprint.json"
        path.write_text(json.dumps({
            "blueprint_id": "concurrency-test",
            "dimension_format_quotas": {
                "fact_extraction": {"single_choice": 1},
                "rule_application": {"case_analysis": 1},
            },
        }), encoding="utf-8")
        return path

    def test_blueprint_requests_run_concurrently_and_keep_task_order(self):
        """蓝图的同案不同题型请求并发执行，但输出按蓝图顺序稳定排列。"""
        import threading
        import time

        active = 0
        max_active = 0
        lock = threading.Lock()

        def fake_generate(case, client, model, dimension_id, questions_count=1,
                           catalog_path=None, question_format=None, **kwargs):
            """模拟阻塞模型请求并记录运行中的最大并发数。"""
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            try:
                # 让第二个请求先结束，验证输出不能按完成顺序写出。
                time.sleep(0.12 if question_format == "single_choice" else 0.02)
                return ([{
                    "question_id": f"{case['case_id']}_{question_format}",
                    "dimension_id": dimension_id,
                    "question_format": question_format,
                }], [])
            finally:
                with lock:
                    active -= 1

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "cases.jsonl"
            output_path = root / "drafts.jsonl"
            write_jsonl(input_path, [self._case("case_1")])
            blueprint = self._blueprint(root)
            with patch.object(_generation_module.llm_client, "load_env"), \
                 patch.object(_generation_module.llm_client, "read_role", return_value=("base", "key", "model")), \
                 patch.object(_generation_module.llm_client, "build_client", return_value=object()), \
                 patch.object(_generation_module, "generate_for_dimension", side_effect=fake_generate):
                rows = run(input_path, output_path, blueprint_path=blueprint, workers=2, qps=1000)
            metadata = json.loads(Path(str(output_path) + ".metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(max_active, 2)
        self.assertEqual([row["question_format"] for row in rows], ["single_choice", "case_analysis"])
        self.assertEqual(metadata["workers"], 2)
        self.assertEqual(metadata["qps"], 1000)
        self.assertEqual(metadata["submitted_tasks"], 2)
        self.assertEqual(metadata["completed_tasks"], 2)
        self.assertEqual(metadata["failed_tasks"], 0)

    def test_one_generation_task_failure_does_not_abort_other_tasks(self):
        """一个维度×题型请求失败时，其他请求仍完成并记录结构化错误。"""
        def fake_generate(case, client, model, dimension_id, questions_count=1,
                           catalog_path=None, question_format=None, **kwargs):
            """模拟一个题型失败而另一个题型正常完成。"""
            if question_format == "single_choice":
                raise RuntimeError("synthetic generation failure")
            return ([{
                "question_id": f"{case['case_id']}_{question_format}",
                "dimension_id": dimension_id,
                "question_format": question_format,
            }], [])

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "cases.jsonl"
            output_path = root / "drafts.jsonl"
            write_jsonl(input_path, [self._case("case_1")])
            blueprint = self._blueprint(root)
            with patch.object(_generation_module.llm_client, "load_env"), \
                 patch.object(_generation_module.llm_client, "read_role", return_value=("base", "key", "model")), \
                 patch.object(_generation_module.llm_client, "build_client", return_value=object()), \
                 patch.object(_generation_module, "generate_for_dimension", side_effect=fake_generate):
                rows = run(input_path, output_path, blueprint_path=blueprint, workers=2, qps=1000)
            errors = read_jsonl(output_path.with_suffix(".errors.jsonl"))
            metadata = json.loads(Path(str(output_path) + ".metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["question_format"], "case_analysis")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["case_id"], "case_1")
        self.assertEqual(errors[0]["dimension_id"], "fact_extraction")
        self.assertEqual(errors[0]["question_format"], "single_choice")
        self.assertEqual(metadata["completed_tasks"], 2)
        self.assertEqual(metadata["failed_tasks"], 1)

    def test_invalid_generation_concurrency_arguments_are_rejected(self):
        """并发参数必须为正数。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "cases.jsonl"
            output_path = root / "drafts.jsonl"
            write_jsonl(input_path, [])
            for kwargs in ({"workers": 0}, {"workers": -1}, {"qps": 0}, {"qps": -1}):
                with self.subTest(kwargs=kwargs):
                    with self.assertRaises(ValueError):
                        run(input_path, output_path, **kwargs)
