"""测试模块：tests/test_legal_ingestion.py。

本文件验证项目中的一个具体行为或模块边界。测试输入通常是内存中的最小样例，测试输出是断言结果，不调用真实模型 API。

项目位置：tests/test_legal_ingestion.py。
主要用途：项目测试模块，验证公共基础层和三条评测线的行为、数据隔离与文档规范。
输入：输入来自测试夹具、临时目录和项目模块。
输出：输出为测试断言结果，不产生正式评测数据。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：通常只创建临时文件或调用测试替身，不调用真实模型 API。
"""

import unittest

from tracks.legal_benchmark.ingestion.clean import parse_judgment

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
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        row = parse_judgment(SAMPLE, source_file="sample.md")
        self.assertEqual(row["document"]["case_no"], "（2024）浙0483民初5218号")
        self.assertEqual(row["full_text"], SAMPLE)
        self.assertIn("诉讼请求", row["sections"]["claims"])
        self.assertIn("本院认为", row["sections"]["court_reasoning"])
        self.assertIn("判决如下", row["sections"]["judgment"])
        self.assertTrue(any("10000" in amount for amount in row["amounts"]))
        self.assertIn("民法典", row["cited_statutes"][0])

    def test_extracts_all_named_parties(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        row = parse_judgment(SAMPLE, source_file="sample.md")
        names = {(party["role"], party["name"]) for party in row["parties"]}
        self.assertIn(("原告", "王某"), names)
        self.assertIn(("被告", "卢某"), names)
        self.assertIn(("被告", "任某"), names)

    def test_records_hash_and_quality_metadata(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        row = parse_judgment(SAMPLE, source_file="sample.md")
        self.assertEqual(len(row["source"]["sha256"]), 64)
        self.assertEqual(row["quality"]["review_status"], "pending")
        self.assertTrue(row["quality"]["parser_version"])


if __name__ == "__main__":
    unittest.main()

