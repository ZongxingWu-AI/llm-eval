"""法律提取批次 metadata、并发和限流回归测试。"""

import importlib
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core import llm_client

_extract = importlib.import_module("methodology.01_造Benchmark.legal.extraction.extract")


class LegalExtractionMetadataTests(unittest.TestCase):
    def test_deterministic_extract_builds_grounded_full_case_fact_map(self):
        """规则提取必须覆盖全文章节，并让每个事实地图条目可回查原文。"""
        case = {
            "case_id": "case_fact_map",
            "full_text": ("原告：甲公司。被告：乙公司。诉讼请求：支付货款十万元。被告辩称货物存在质量问题。经审理查明双方于2025年1月1日签订合同。原告提交送货单证明已经交货。本院认为送货单真实，应予采信。《民法典》第五百零九条应予适用。判决乙公司支付货款十万元。如不服本判决，可在十五日内上诉。"),
            "sections": {
                "header": "原告：甲公司。被告：乙公司。",
                "claims": "诉讼请求：支付货款十万元。",
                "defenses": "被告辩称货物存在质量问题。",
                "facts": "经审理查明双方于2025年1月1日签订合同。",
                "evidence": "原告提交送货单证明已经交货。",
                "court_reasoning": "本院认为送货单真实，应予采信。《民法典》第五百零九条应予适用。",
                "judgment": "判决乙公司支付货款十万元。",
                "tail": "如不服本判决，可在十五日内上诉。",
            },
            "parties": [{"role": "原告", "name": "甲公司"}, {"role": "被告", "name": "乙公司"}],
        }
        extracted = _extract.deterministic_extract(case)
        self.assertIn("legal_issues", extracted)
        self.assertIn("evidence_findings", extracted)
        self.assertIn("conclusions", extracted)
        fact_map = extracted["case_fact_map"]
        expected_groups = {"key_facts", "party_relationships", "claims", "defenses", "evidence", "court_found_facts", "procedural_timeline", "applied_laws", "court_reasoning", "judgment_results"}
        self.assertEqual(set(fact_map), expected_groups)
        for group in ("key_facts", "claims", "defenses", "evidence", "applied_laws", "judgment_results", "procedural_timeline"):
            self.assertTrue(fact_map[group])
        for entries in fact_map.values():
            for entry in entries:
                self.assertEqual(set(entry), {"text", "source_section", "source_quote"})
                self.assertIn(entry["source_quote"], case["sections"][entry["source_section"]])

    def test_extract_case_keeps_fact_map_when_llm_returns_legacy_fields_only(self):
        """旧版模型只返回三组字段时，新的全文事实地图也不能被覆盖丢失。"""
        case = {"case_id": "case_legacy_llm", "full_text": "经审理查明甲已交货。本院认为乙应付款。判决乙支付货款。", "sections": {"facts": "经审理查明甲已交货。", "court_reasoning": "本院认为乙应付款。", "judgment": "判决乙支付货款。"}}
        candidate = {"legal_issues": ["付款责任"], "evidence_findings": [], "conclusions": [{"conclusion": "乙支付货款", "source_section": "judgment", "source_quote": "判决乙支付货款。"}]}
        with patch.object(_extract.llm_client, "call_model", return_value=(json.dumps(candidate), 0, 0, "stop")), patch.object(_extract, "load_template", return_value="{{case_sections}}"):
            result = _extract.extract_case(case, client=object(), model="model")
        self.assertEqual(result["legal_extraction"]["legal_issues"], ["付款责任"])
        self.assertTrue(result["legal_extraction"]["case_fact_map"]["key_facts"])

    def _run_with_methods(self, methods, **run_kwargs):
        """在临时 JSONL 上模拟不同逐案提取方法并读取批次 metadata。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.jsonl"
            output_path = root / "output.jsonl"
            input_path.write_text(
                "\n".join(json.dumps({"case_id": f"case_{i}"}, ensure_ascii=False) for i in range(len(methods))) + "\n",
                encoding="utf-8",
            )

            def fake_extract(case, client=None, model="", **kwargs):
                """按测试给定的方法模拟单条案件提取结果。"""
                method = methods[int(case["case_id"].split("_")[-1])]
                return {
                    **case,
                    "quality": {"extraction": {"method": method}},
                }

            with patch.object(_extract, "extract_case", side_effect=fake_extract), \
                 patch.object(_extract.llm_client, "load_env"), \
                 patch.object(_extract.llm_client, "read_role", return_value=("base", "key", "model")), \
                 patch.object(_extract.llm_client, "build_client", return_value=object()):
                results = _extract.run(input_path, output_path, use_llm=True, **run_kwargs)

            metadata = json.loads(output_path.with_suffix(output_path.suffix + ".metadata.json").read_text(encoding="utf-8"))
            return results, metadata

    def test_metadata_uses_actual_rules_result_even_when_llm_requested(self):
        """验证请求模型但逐案规则降级时，批次 metadata 如实记录规则方法。"""
        _, metadata = self._run_with_methods(["rules"], workers=1)
        self.assertEqual(metadata["method"], "rules")
        self.assertEqual(metadata["method_counts"], {"rules": 1, "llm_grounded": 0})

    def test_metadata_reports_all_llm_results(self):
        """验证全部案件由模型成功提取时，批次 metadata 记录模型方法。"""
        _, metadata = self._run_with_methods(["llm_grounded", "llm_grounded"], workers=1)
        self.assertEqual(metadata["method"], "llm_grounded")
        self.assertEqual(metadata["method_counts"], {"rules": 0, "llm_grounded": 2})

    def test_metadata_reports_mixed_results(self):
        """验证同一批次混合模型和规则结果时，批次 metadata 记录 mixed。"""
        _, metadata = self._run_with_methods(["rules", "llm_grounded", "rules"], workers=1)
        self.assertEqual(metadata["method"], "mixed")
        self.assertEqual(metadata["method_counts"], {"rules": 2, "llm_grounded": 1})

    def test_llm_runs_in_parallel_and_preserves_input_order(self):
        """验证 LLM 批处理并发执行，但输出仍保持输入顺序。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.jsonl"
            output_path = root / "output.jsonl"
            rows = [{"case_id": f"case_{i}"} for i in range(4)]
            input_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            active = 0
            max_active = 0
            lock = threading.Lock()

            def fake_extract(case, client=None, model="", **kwargs):
                """模拟单案提取，供并发调度测试使用。"""
                nonlocal active, max_active
                with lock:
                    active += 1
                    max_active = max(max_active, active)
                time.sleep(0.08 if case["case_id"] == "case_0" else 0.01)
                with lock:
                    active -= 1
                return {**case, "quality": {"extraction": {"method": "llm_grounded"}}}

            with patch.object(_extract, "extract_case", side_effect=fake_extract), \
                 patch.object(_extract.llm_client, "load_env"), \
                 patch.object(_extract.llm_client, "read_role", return_value=("base", "key", "model")), \
                 patch.object(_extract.llm_client, "build_client", return_value=object()):
                results = _extract.run(input_path, output_path, use_llm=True, workers=2, qps=1000)

            self.assertGreaterEqual(max_active, 2)
            self.assertLessEqual(max_active, 2)
            self.assertEqual([row["case_id"] for row in results], [row["case_id"] for row in rows])

    def test_workers_one_keeps_llm_serial(self):
        """验证 workers=1 时不产生并发。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.jsonl"
            output_path = root / "output.jsonl"
            input_path.write_text("\n".join(json.dumps({"case_id": f"case_{i}"}) for i in range(3)) + "\n", encoding="utf-8")
            active = 0
            max_active = 0
            lock = threading.Lock()

            def fake_extract(case, client=None, model="", **kwargs):
                """模拟单案提取，供并发调度测试使用。"""
                nonlocal active, max_active
                with lock:
                    active += 1
                    max_active = max(max_active, active)
                time.sleep(0.01)
                with lock:
                    active -= 1
                return {**case, "quality": {"extraction": {"method": "llm_grounded"}}}

            with patch.object(_extract, "extract_case", side_effect=fake_extract), \
                 patch.object(_extract.llm_client, "load_env"), \
                 patch.object(_extract.llm_client, "read_role", return_value=("base", "key", "model")), \
                 patch.object(_extract.llm_client, "build_client", return_value=object()):
                _extract.run(input_path, output_path, use_llm=True, workers=1, qps=1000)

            self.assertEqual(max_active, 1)

    def test_single_worker_failure_does_not_abort_batch(self):
        """验证单案意外异常时，其他案件仍完成且失败案保留规则降级结果。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.jsonl"
            output_path = root / "output.jsonl"
            rows = [{"case_id": f"case_{i}", "sections": {}} for i in range(3)]
            input_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            def fake_extract(case, client=None, model="", **kwargs):
                """模拟单案提取，供并发调度测试使用。"""
                if case["case_id"] == "case_1":
                    raise RuntimeError("synthetic worker failure")
                return {**case, "quality": {"extraction": {"method": "llm_grounded"}}}

            with patch.object(_extract, "extract_case", side_effect=fake_extract), \
                 patch.object(_extract.llm_client, "load_env"), \
                 patch.object(_extract.llm_client, "read_role", return_value=("base", "key", "model")), \
                 patch.object(_extract.llm_client, "build_client", return_value=object()):
                results = _extract.run(input_path, output_path, use_llm=True, workers=2, qps=1000)

            self.assertEqual(len(results), 3)
            failed = results[1]
            self.assertEqual(failed["quality"]["extraction"]["method"], "rules")
            self.assertTrue(failed["quality"]["extraction"]["errors"])

    def test_invalid_concurrency_arguments_are_rejected(self):
        """验证 workers 和 qps 的非法值有明确参数错误。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.jsonl"
            output_path = root / "output.jsonl"
            input_path.write_text(json.dumps({"case_id": "case_0"}) + "\n", encoding="utf-8")
            for kwargs in ({"workers": 0}, {"workers": -1}, {"qps": 0}, {"qps": -1}):
                with self.subTest(kwargs=kwargs):
                    with self.assertRaises(ValueError):
                        _extract.run(input_path, output_path, **kwargs)

    def test_rules_mode_does_not_create_executor(self):
        """验证规则模式保持串行且不创建线程池。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.jsonl"
            output_path = root / "output.jsonl"
            input_path.write_text(json.dumps({"case_id": "case_0", "sections": {}}) + "\n", encoding="utf-8")
            with patch.object(_extract, "ThreadPoolExecutor") as executor:
                _extract.run(input_path, output_path, use_llm=False)
            executor.assert_not_called()

    def test_qps_limiter_spaces_request_starts(self):
        """验证限流器按 qps 为请求启动时间留出间隔。"""
        limiter = _extract._QPSLimiter(2)
        with patch.object(_extract.time, "monotonic", side_effect=[0.0, 0.0]), \
             patch.object(_extract.time, "sleep") as sleep:
            limiter.wait()
            limiter.wait()
        sleep.assert_called_once_with(0.5)

    def test_metadata_records_concurrency_settings(self):
        """验证运行 metadata 保存实际 workers 和 qps。"""
        _, metadata = self._run_with_methods(["rules"], workers=2, qps=3.5)
        self.assertEqual(metadata["workers"], 2)
        self.assertEqual(metadata["qps"], 3.5)


    def test_invalid_llm_sources_fall_back_to_rules(self):
        """验证模型引用无法回查时保留规则结果并标记 rules。"""
        case = {
            "case_id": "case_0",
            "sections": {
                "court_reasoning": "关于付款责任。证据不足。",
                "judgment": "判决：驳回诉讼请求。",
            },
        }
        candidate = {
            "legal_issues": ["模型无法回查的争议"],
            "evidence_findings": [{
                "conclusion": "模型证据判断",
                "source_section": "court_reasoning",
                "source_quote": "不存在的证据原文",
            }],
            "conclusions": [{
                "conclusion": "模型裁判结论",
                "source_section": "judgment",
                "source_quote": "不存在的判决原文",
            }],
        }
        with patch.object(_extract.llm_client, "call_model", return_value=(json.dumps(candidate), 0, 0, "stop")), \
             patch.object(_extract, "load_template", return_value="template"), \
             patch.object(_extract, "render", return_value="prompt"):
            result = _extract.extract_case(case, client=object(), model="model")

        expected = _extract.deterministic_extract(case)
        self.assertEqual(result["legal_extraction"], expected)
        self.assertEqual(result["quality"]["extraction"]["method"], "rules")
        self.assertTrue(result["quality"]["extraction"]["errors"])

class LLMClientHookTests(unittest.TestCase):
    def test_before_attempt_hook_runs_for_each_retry(self):
        """验证请求前钩子覆盖首次请求和每次重试。"""
        attempts = []
        hook_calls = []

        class Completions:
            def create(self, **kwargs):
                """模拟模型请求失败，以验证重试钩子。"""
                attempts.append(kwargs)
                raise RuntimeError("temporary failure")

        class Chat:
            completions = Completions()

        class Client:
            chat = Chat()

        with patch.object(llm_client.time, "sleep"):
            with self.assertRaises(RuntimeError):
                llm_client.call_model(
                    Client(), "model", "prompt", 0, 10,
                    before_attempt=lambda: hook_calls.append(len(hook_calls)),
                )

        self.assertEqual(len(attempts), 3)
        self.assertEqual(len(hook_calls), 3)


if __name__ == "__main__":
    unittest.main()

