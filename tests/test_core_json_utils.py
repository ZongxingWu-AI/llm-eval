"""测试模块：tests/test_core_json_utils.py。

本文件验证项目中的一个具体行为或模块边界。测试输入通常是内存中的最小样例，测试输出是断言结果，不调用真实模型 API。

项目位置：tests/test_core_json_utils.py。
主要用途：项目测试模块，验证公共基础层和三条评测线的行为、数据隔离与文档规范。
输入：输入来自测试夹具、临时目录和项目模块。
输出：输出为测试断言结果，不产生正式评测数据。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：通常只创建临时文件或调用测试替身，不调用真实模型 API。
"""

import unittest

from core.json_utils import parse_json_object, parse_json_value

class CoreJsonUtilsTests(unittest.TestCase):

    def test_parses_fenced_json_object(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        raw = "说明\n```json\n{\"score\": 3, \"ok\": true}\n```\n"
        self.assertEqual(parse_json_object(raw), {"score": 3, "ok": True})

    def test_parses_json_embedded_in_explanation(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        raw = '最终结果如下：{"winner": "A", "reason": "完整"}。'
        self.assertEqual(
            parse_json_object(raw),
            {"winner": "A", "reason": "完整"},
        )

    def test_parses_fenced_json_array(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        raw = "```json\n[{\"id\": 1}, {\"id\": 2}]\n```"
        self.assertEqual(parse_json_value(raw), [{"id": 1}, {"id": 2}])

    def test_rejects_missing_json_object(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        with self.assertRaises(ValueError):
            parse_json_object("没有结构化结果")


if __name__ == "__main__":
    unittest.main()
