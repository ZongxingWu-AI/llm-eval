"""法律 Benchmark 改造的自动化回归测试。"""

import importlib
import unittest

_redactor = importlib.import_module("methodology.01_造Benchmark.legal.ingestion.pii_redaction")
_clean = importlib.import_module("methodology.01_造Benchmark.legal.ingestion.clean")


class LegalPrivacyTests(unittest.TestCase):
    def test_same_value_and_distinct_addresses_get_stable_distinct_placeholders(self):
        """验证 test_same_value_and_distinct_addresses_get_stable_distinct_placeholders 的预期行为。"""
        text = "住址：北京市朝阳区幸福路一号；另住址：上海市浦东新区海棠路二号；再次住址：北京市朝阳区幸福路一号。"
        redacted, _ = _redactor.redact_pii(text)
        self.assertEqual(redacted.count("地址一"), 2)
        self.assertEqual(redacted.count("地址二"), 1)
        self.assertEqual(_redactor.contains_pii(redacted), [])

    def test_clean_uses_one_redacted_external_text_without_external_sections(self):
        """验证 clean 只输出一份脱敏全文，不再复制 external_sections。"""
        text = (
            "原告：张三\n被告：李四\n诉讼请求：李四支付货款。\n"
            "经审理查明：张三住址：北京市朝阳区幸福路一号，李四手机号：13812345678。\n"
            "本院认为：被告应付款。\n判决如下：李四支付货款。"
        )
        row = _clean.parse_judgment(text, "case.txt")
        self.assertNotIn("13812345678", row["external_text"])
        legacy_text_field = "legacy_external_text"
        self.assertNotIn(legacy_text_field, row)
        self.assertNotIn("external_sections", row)
        self.assertIn("手机号一", row["external_text"])
        self.assertIn("幸福路一号", row["full_text"])
        self.assertNotIn("幸福路一号", row["external_text"])

    def test_old_text_field_is_not_used_as_fallback(self):
        """旧文本字段不应再作为 external_text 的兼容回退。"""
        legacy_text_field = "legacy_external_text"
        row = {"full_text": "内部原文", legacy_text_field: "旧脱敏文本"}
        generation = importlib.import_module("methodology.02_构建题集.legal.generation.generate")
        with self.assertRaisesRegex(ValueError, "缺少 external_text"):
            generation.build_generation_input(row)


if __name__ == "__main__":
    unittest.main()




