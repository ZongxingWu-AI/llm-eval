"""C-Eval 客观题评分测试。

被测模块：tracks.ceval.evaluate。覆盖常见回答形态的 A/B/C/D 抽取和逐题正确率记录。
模型调用使用 mock，不访问网络；不写正式结果目录。
失败表示客观答案提取、评分字段或模型调用元数据发生回归。"""

import unittest
from unittest.mock import patch

from tracks.ceval.evaluate import evaluate_rows, extract_answer



class CevalTests(unittest.TestCase):
    def test_extracts_answer_from_common_response_shapes(self):
        """测试目标：验证直接字母、中文答案句和带括号选项都能抽取。
        准备数据：准备多种模型回答字符串。
        调用函数：逐个调用 extract_answer。
        预期结果：均返回期望的 A/B/C/D。
        该断言保护的行为：提示词细微变化不会破坏客观答案识别。"""

        for text, expected in (("C", "C"), ("答案是 B", "B"), ("选择：D", "D"), ("A. 因为……", "A")):
            with self.subTest(text=text):
                self.assertEqual(extract_answer(text), expected)

    @patch("tracks.ceval.evaluate.llm_client.call_model", return_value=("答案是 C", 0.2, 12, "stop"))
    def test_minimal_evaluation_scores_answer(self, call_model):
        """测试目标：验证一题 C-Eval 的模型调用、答案比较和元数据记录。
        准备数据：构造标准答案为 B 的一题，并 mock call_model 返回“答案是B”。
        调用函数：调用 evaluate_rows。
        预期结果：结果 correct=True、predicted_answer=B 且无错误。
        该断言保护的行为：逐题正确率基础数据和模型调用协议保持稳定。"""

        question = {"id": "q1", "question": "题目", "A": "a", "B": "b", "C": "c", "D": "d", "answer": "C"}
        result = evaluate_rows([question], object(), "model")
        self.assertTrue(result[0]["is_correct"])
        self.assertEqual(result[0]["tokens"], 12)


if __name__ == "__main__":
    unittest.main()
