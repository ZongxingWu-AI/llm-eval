"""Pairwise Judge 核心行为测试。

被测模块：pairwise、bias_stats。覆盖 fenced JSON、双轮位置交换映射、多数投票和位置偏见统计。
裁判模型使用 mock，不访问真实 API，也不创建正式结果文件。
失败表示位置标签可能被错误当成原始选手，或汇总统计发生变化。"""

import unittest
from unittest.mock import patch

from tracks.pairwise_judge import bias_stats
from tracks.pairwise_judge.pairwise import judge_one, majority_winner, parse_judge_json



class PairwiseTests(unittest.TestCase):
    def test_parses_fenced_json(self):
        """测试目标：验证裁判 fenced JSON 能解析 winner、分数和理由。
        准备数据：准备包含 winner=A 的 Markdown JSON 响应。
        调用函数：调用 parse_judge_json。
        预期结果：返回对象并保留胜者字段。
        该断言保护的行为：裁判常用代码围栏不会被误判为解析错误。"""

        self.assertEqual(parse_judge_json('```json\n{"winner":"A"}\n```'), {"winner": "A"})

    @patch("tracks.pairwise_judge.pairwise.llm_client.call_model")
    def test_position_swap_maps_second_round_back_to_original_contestants(self, call_model):
        """测试目标：验证第二轮交换位置后，位置 B 能正确映射回原始选手 A。
        准备数据：mock 两轮裁判依次返回位置 A 和位置 B。
        调用函数：调用 judge_one。
        预期结果：round1_winner 与 round2_winner 均为原始 A，最终胜者为 A。
        该断言保护的行为：A/B 位置标签不会覆盖原始参赛者身份。"""

        call_model.side_effect = [
            ('{"winner":"A","score_a":{"x":5},"score_b":{"x":2},"analysis":"first"}', 0, 0, "stop"),
            ('{"winner":"B","score_a":{"x":2},"score_b":{"x":5},"analysis":"second"}', 0, 0, "stop"),
        ]
        result = judge_one({"question": "q", "answer_a": "a", "answer_b": "b"}, object(), "judge")
        self.assertEqual(result["judge_winner"], "A")
        self.assertFalse(result["position_bias"])
        self.assertEqual(result["round2_winner"], "A")

    @patch("tracks.pairwise_judge.pairwise.llm_client.call_model")
    def test_disagreement_after_position_swap_flags_position_bias(self, call_model):
        """测试目标：验证两轮都偏好位置 A 时会映射成原始双方各胜一轮。
        准备数据：mock 两轮裁判均返回位置 A。
        调用函数：调用 judge_one。
        预期结果：最终 tie 且 position_bias=True。
        该断言保护的行为：位置偏见可被双轮交换检测，而不是错误判某位选手获胜。"""

        call_model.side_effect = [
            ('{"winner":"A"}', 0, 0, "stop"),
            ('{"winner":"A"}', 0, 0, "stop"),
        ]
        result = judge_one({"question": "q", "answer_a": "a", "answer_b": "b"}, object(), "judge")
        self.assertEqual(result["judge_winner"], "tie")
        self.assertTrue(result["position_bias"])

    def test_majority_vote(self):
        """测试目标：验证多个有效裁判结果按原始选手进行多数投票。
        准备数据：准备两个 A 胜和一个 B 胜的结果。
        调用函数：调用 majority_winner。
        预期结果：返回 A。
        该断言保护的行为：多裁判汇总不会受单个裁判顺序影响。"""

        self.assertEqual(majority_winner(["A", "A", "B"]), "A")
        self.assertEqual(majority_winner(["A", "B"]), "tie")

    def test_bias_statistics_preserve_expected_counts(self):
        """测试目标：验证位置偏见与胜负数量的统计口径。
        准备数据：准备包含 A 胜、平局和 position_bias 标记的逐题结果。
        调用函数：调用 compute_stats。
        预期结果：总数、胜负和平局及偏见计数符合样例。
        该断言保护的行为：报告使用的统计字段不会在重构中改变含义。"""

        rows = [{"model_a": "alpha-large", "model_b": "beta-large"}]
        results = [{
            "error": "", "judge1_position_bias": True, "final_winner": "A",
            "answer_a_len": 20, "answer_b_len": 10,
            "judge1_winner": "A", "judge2_winner": "", "judge3_winner": "",
        }]
        stats = bias_stats.compute_stats(results, rows, [(object(), "alpha-judge")])
        self.assertEqual(stats["bias_count"], 1)
        self.assertEqual(stats["longer_wins"], 1)
        self.assertEqual(stats["judge_same_wins"][0], 1)


if __name__ == "__main__":
    unittest.main()
