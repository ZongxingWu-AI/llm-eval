"""公共 JSON 解析测试。

被测模块：core.json_utils。测试纯文本、Markdown 围栏、混杂解释和数组解析，以及缺少 JSON 时的失败行为。
所有输入均为内存字符串，不使用临时文件或 mock，不调用真实模型。
失败通常表示模型响应兼容性或错误边界被破坏。"""

import unittest

from core.json_utils import parse_json_object, parse_json_value

class CoreJsonUtilsTests(unittest.TestCase):

    def test_parses_fenced_json_object(self):
        """测试目标：确认 Markdown json 围栏中的对象可直接解析。
        准备数据：构造包含 winner 和 reason 的 fenced JSON 字符串。
        调用函数：调用 parse_json_object。
        预期结果：返回字典且 winner 保持为 A。
        该断言保护的行为：裁判模型常见的代码围栏不会导致解析失败。"""

        raw = "说明\n```json\n{\"score\": 3, \"ok\": true}\n```\n"
        self.assertEqual(parse_json_object(raw), {"score": 3, "ok": True})

    def test_parses_json_embedded_in_explanation(self):
        """测试目标：确认解释文字中嵌入的对象可由平衡括号扫描找到。
        准备数据：构造前后带自然语言说明的 JSON 对象。
        调用函数：调用 parse_json_object。
        预期结果：返回内部字典而忽略外围解释。
        该断言保护的行为：模型先解释后输出 JSON 时评测仍可继续。"""

        raw = '最终结果如下：{"winner": "A", "reason": "完整"}。'
        self.assertEqual(
            parse_json_object(raw),
            {"winner": "A", "reason": "完整"},
        )

    def test_parses_fenced_json_array(self):
        """测试目标：确认通用解析器支持 fenced JSON 数组。
        准备数据：构造含一个对象的 Markdown 数组。
        调用函数：调用 parse_json_value。
        预期结果：返回列表且首项 id 正确。
        该断言保护的行为：法律出题模型返回数组时不会被强制当成对象。"""

        raw = "```json\n[{\"id\": 1}, {\"id\": 2}]\n```"
        self.assertEqual(parse_json_value(raw), [{"id": 1}, {"id": 2}])

    def test_rejects_missing_json_object(self):
        """测试目标：确认要求对象时不会接受完全没有 JSON 的文本。
        准备数据：准备普通说明字符串。
        调用函数：调用 parse_json_object。
        预期结果：抛出 ValueError。
        该断言保护的行为：无结构化结果时必须显式失败，不能静默生成空字典。"""

        with self.assertRaises(ValueError):
            parse_json_object("没有结构化结果")


if __name__ == "__main__":
    unittest.main()
