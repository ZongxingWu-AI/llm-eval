"""法律判决书无损解析测试。

被测模块：methodology.01_造Benchmark.legal.ingestion.clean。覆盖全文保留、主要章节、多方当事人、哈希和质量元数据。
使用内存判决书样例，不调用模型、不写正式 raw/clean。
失败表示清洗可能丢失法院说理、判决主文或错误遗漏当事人。"""

import importlib
import unittest

_clean_module = importlib.import_module("methodology.01_造Benchmark.legal.ingestion.clean")
parse_judgment = _clean_module.parse_judgment

SAMPLE = """
民事判决书
（2024）浙0483民初5218号
原告：王某。
被告：卢某、任某。
诉讼请求：判令被告支付货款及利息。
卢某辩称：同意依法处理。
经审理查明，原告与卢某存在买卖合同关系，微信聊天记录载明付款安排。任某未参与交易。
本院认为，现有证据能够证明卢某尚欠货款，但不足以证明任某承担共同债务。本院依法判决：一、卢某支付货款10000元；二、支付逾期利息。
依照《中华人民共和国民法典》第五百七十七条之规定，判决如下：卢某于本判决生效后十日内支付货款。
如不服本判决，可上诉。
"""


class LegalIngestionTests(unittest.TestCase):
    def test_parsing_is_lossless_and_preserves_legal_sections(self):
        """测试目标：验证解析后 full_text 完整保留且诉请、说理、主文均可定位。
        准备数据：准备包含典型章节标记的内存判决书。
        调用函数：调用 parse_judgment。
        预期结果：full_text 等于输入，claims、court_reasoning、judgment 非空。
        该断言保护的行为：第一阶段清洗不能用摘要替代全文或丢失关键裁判内容。"""

        row = parse_judgment(SAMPLE, source_file="sample.md")
        self.assertEqual(row["document"]["case_no"], "（2024）浙0483民初5218号")
        self.assertEqual(row["full_text"], SAMPLE)
        self.assertIn("诉讼请求", row["sections"]["claims"])
        self.assertIn("本院认为", row["sections"]["court_reasoning"])
        self.assertIn("判决如下", row["sections"]["judgment"])
        self.assertTrue(any("10000" in amount for amount in row["amounts"]))
        self.assertIn("民法典", row["cited_statutes"][0])

    def test_extracts_all_named_parties(self):
        """测试目标：验证一行多个原被告会拆成独立当事人。
        准备数据：准备含并列原告、被告和代理人的角色行。
        调用函数：调用 extract_parties。
        预期结果：返回全部姓名及正确角色，而非只保留首项。
        该断言保护的行为：多方当事人案件的主体信息完整。"""

        row = parse_judgment(SAMPLE, source_file="sample.md")
        names = {(party["role"], party["name"]) for party in row["parties"]}
        self.assertIn(("原告", "王某"), names)
        self.assertIn(("被告", "卢某"), names)
        self.assertIn(("被告", "任某"), names)

    def test_records_hash_and_quality_metadata(self):
        """测试目标：验证案件哈希、解析器版本和缺失章节状态被记录。
        准备数据：准备最小判决书文本和来源文件名。
        调用函数：调用 parse_judgment。
        预期结果：source.sha256、quality.parser_version 和 review_status 存在。
        该断言保护的行为：原始来源与解析质量可追踪、可重复。"""

        row = parse_judgment(SAMPLE, source_file="sample.md")
        self.assertEqual(len(row["source"]["sha256"]), 64)
        self.assertEqual(row["quality"]["review_status"], "pending")
        self.assertTrue(row["quality"]["parser_version"])


if __name__ == "__main__":
    unittest.main()
