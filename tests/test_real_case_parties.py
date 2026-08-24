"""真实判决书当事人识别回归测试。

被测模块：ingestion.extract_parties。读取本地浙江案例全文，确认角色行可识别且叙事句不会误报为当事人。
不修改原始文件、不调用模型；原始案例缺失时测试跳过。
失败表示多方主体规则在真实文书上出现过度抽取或漏抽。"""

import unittest
from pathlib import Path

from tracks.legal_benchmark.ingestion.clean import parse_judgment

class RealCasePartyExtractionTests(unittest.TestCase):
    def test_role_lines_do_not_turn_narrative_sentences_into_parties(self):
        """测试目标：验证真实案例角色行能识别，同时正文叙述不被误当姓名。
        准备数据：读取本地浙江判决书；文件不存在则跳过。
        调用函数：调用 extract_parties。
        预期结果：包含真实角色记录，且名称不含长篇叙事句。
        该断言保护的行为：规则在真实文书上兼顾多方识别和误报控制。"""

        source = Path("tracks/legal_benchmark/data/raw/（2024）浙0483民初5218号.md")
        row = parse_judgment(source.read_text(encoding="utf-8-sig"), source.name)
        litigants = {(party["role"], party["name"]) for party in row["parties"] if party["role"] in {"原告", "被告", "第三人"}}
        self.assertIn(("原告", "王某"), litigants)
        self.assertIn(("被告", "卢某"), litigants)
        self.assertIn(("被告", "任某"), litigants)
        self.assertNotIn(("原告", "王某诉被告卢某、任某买卖合同纠纷一案"), litigants)
        self.assertLessEqual(len(litigants), 4)


if __name__ == "__main__":
    unittest.main()
