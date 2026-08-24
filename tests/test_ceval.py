"""测试模块：tests/test_ceval.py。

本文件验证项目中的一个具体行为或模块边界。测试输入通常是内存中的最小样例，测试输出是断言结果，不调用真实模型 API。

项目位置：tests/test_ceval.py。
主要用途：项目测试模块，验证公共基础层和三条评测线的行为、数据隔离与文档规范。
输入：输入来自测试夹具、临时目录和项目模块。
输出：输出为测试断言结果，不产生正式评测数据。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：通常只创建临时文件或调用测试替身，不调用真实模型 API。
"""

import unittest
from unittest.mock import patch

from tracks.ceval.evaluate import evaluate_rows, extract_answer



class CevalTests(unittest.TestCase):
    def test_extracts_answer_from_common_response_shapes(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        for text, expected in (("C", "C"), ("答案是 B", "B"), ("选择：D", "D"), ("A. 因为……", "A")):
            with self.subTest(text=text):
                self.assertEqual(extract_answer(text), expected)

    @patch("tracks.ceval.evaluate.llm_client.call_model", return_value=("答案是 C", 0.2, 12, "stop"))
    def test_minimal_evaluation_scores_answer(self, call_model):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self、call_model。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        question = {"id": "q1", "question": "题目", "A": "a", "B": "b", "C": "c", "D": "d", "answer": "C"}
        result = evaluate_rows([question], object(), "model")
        self.assertTrue(result[0]["is_correct"])
        self.assertEqual(result[0]["tokens"], 12)


if __name__ == "__main__":
    unittest.main()
