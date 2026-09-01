"""事实地图 Prompt 与 clean 输出契约测试。"""

import importlib
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTRACTION_PROMPT = ROOT / "methodology/01_造Benchmark/legal/prompts/legal_extraction_prompt.md"
GENERATION_PROMPT = ROOT / "methodology/01_造Benchmark/legal/prompts/legal_generation_prompt.md"


class FactMapPromptContractTests(unittest.TestCase):
    def test_extraction_prompt_describes_current_fact_map_contract(self):
        """验证抽取 Prompt 只描述当前事实地图契约。"""
        prompt = EXTRACTION_PROMPT.read_text(encoding="utf-8")
        required = {
            "key_facts",
            "party_relationships",
            "claims",
            "defenses",
            "disputed_issues",
            "evidence",
            "court_found_facts",
            "procedural_timeline",
            "applied_laws",
            "court_reasoning",
            "judgment_results",
        }
        for field in required:
            self.assertIn(field, prompt)

        json_blocks = re.findall(r"```json\s*(.*?)\s*```", prompt, flags=re.DOTALL)
        self.assertTrue(json_blocks, "抽取 Prompt 应包含 canonical JSON 示例")
        canonical_json = json_blocks[0]
        self.assertNotIn("source_quote_sha256", canonical_json)
        self.assertIn("程序", prompt)
        self.assertIn("哈希", prompt)

    def test_extraction_prompt_uses_only_external_text_source(self):
        """抽取 Prompt 的原文占位符只能是完整脱敏全文。"""
        prompt = EXTRACTION_PROMPT.read_text(encoding="utf-8")
        self.assertIn("{{external_text}}", prompt)
        self.assertNotIn("{{full_text}}", prompt)
        self.assertNotIn("{{sections}}", prompt)
        self.assertNotIn("{{external_sections}}", prompt)
    def test_generation_prompt_is_not_a_current_executable_contract(self):
        """验证非当前出题 Prompt 不会被误当作可执行输入输出契约。"""
        prompt = GENERATION_PROMPT.read_text(encoding="utf-8")
        self.assertNotIn("{{generation_input}}", prompt)
        self.assertNotIn("## 输出协议", prompt)


if __name__ == "__main__":
    unittest.main()







