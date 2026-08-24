"""测试模块：tests/test_legal_manifest.py。

本文件验证项目中的一个具体行为或模块边界。测试输入通常是内存中的最小样例，测试输出是断言结果，不调用真实模型 API。

项目位置：tests/test_legal_manifest.py。
主要用途：项目测试模块，验证公共基础层和三条评测线的行为、数据隔离与文档规范。
输入：输入来自测试夹具、临时目录和项目模块。
输出：输出为测试断言结果，不产生正式评测数据。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：通常只创建临时文件或调用测试替身，不调用真实模型 API。
"""

import tempfile
import unittest
from pathlib import Path

from core.data_io import read_jsonl
from tracks.legal_benchmark.ingestion.clean import clean_directory



DOCUMENT_TEMPLATE = """某某人民法院\n民事判决书\n（2024）浙0000民初1号\n原告：王某。\n被告：李某。\n诉讼请求：支付货款{amount}元。\n经审理查明，双方存在买卖关系。\n本院认为，被告应当付款。\n判决如下：被告支付货款{amount}元。\n"""


class LegalManifestTests(unittest.TestCase):
    def test_same_filename_with_changed_content_is_reprocessed(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "raw"
            raw.mkdir()
            source = raw / "same.md"
            parsed = root / "parsed.jsonl"
            manifest = root / "manifest.jsonl"
            source.write_text(DOCUMENT_TEMPLATE.format(amount=100), encoding="utf-8")
            first = clean_directory(raw, parsed, manifest_output=manifest)[0]
            source.write_text(DOCUMENT_TEMPLATE.format(amount=200), encoding="utf-8")
            second = clean_directory(raw, parsed, manifest_output=manifest)[0]
            self.assertNotEqual(first["source"]["sha256"], second["source"]["sha256"])
            self.assertNotEqual(first["case_id"], second["case_id"])
            rows = read_jsonl(manifest)
            self.assertEqual(rows[0]["sha256"], second["source"]["sha256"])
            self.assertEqual(rows[0]["source_file"], "same.md")


if __name__ == "__main__":
    unittest.main()
