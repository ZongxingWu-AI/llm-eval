"""测试模块：tests/test_pairwise.py。

本文件验证项目中的一个具体行为或模块边界。测试输入通常是内存中的最小样例，测试输出是断言结果，不调用真实模型 API。

项目位置：tests/test_pairwise.py。
主要用途：项目测试模块，验证公共基础层和三条评测线的行为、数据隔离与文档规范。
输入：输入来自测试夹具、临时目录和项目模块。
输出：输出为测试断言结果，不产生正式评测数据。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：通常只创建临时文件或调用测试替身，不调用真实模型 API。
"""

import unittest
from unittest.mock import patch

from tracks.pairwise_judge import bias_stats
from tracks.pairwise_judge.pairwise import judge_one, majority_winner, parse_judge_json



class PairwiseTests(unittest.TestCase):
    def test_parses_fenced_json(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        self.assertEqual(parse_judge_json('```json\n{"winner":"A"}\n```'), {"winner": "A"})

    @patch("tracks.pairwise_judge.pairwise.llm_client.call_model")
    def test_position_swap_maps_second_round_back_to_original_contestants(self, call_model):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self、call_model。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

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
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self、call_model。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        call_model.side_effect = [
            ('{"winner":"A"}', 0, 0, "stop"),
            ('{"winner":"A"}', 0, 0, "stop"),
        ]
        result = judge_one({"question": "q", "answer_a": "a", "answer_b": "b"}, object(), "judge")
        self.assertEqual(result["judge_winner"], "tie")
        self.assertTrue(result["position_bias"])

    def test_majority_vote(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        self.assertEqual(majority_winner(["A", "A", "B"]), "A")
        self.assertEqual(majority_winner(["A", "B"]), "tie")

    def test_bias_statistics_preserve_expected_counts(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

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
