"""法律原始案例 manifest 回归测试。

被测模块：clean_directory。使用 TemporaryDirectory 创建同名但内容变化的本地案例与输出文件。
不调用模型，不接触正式 raw 数据。
失败表示解析器可能只按文件名跳过变化内容，破坏哈希和 case_id 的可追溯性。"""

import tempfile
import importlib
import unittest
from pathlib import Path

from core.data_io import read_jsonl
_clean_module = importlib.import_module("methodology.01_造Benchmark.legal.ingestion.clean")
clean_directory = _clean_module.clean_directory



DOCUMENT_TEMPLATE = """某某人民法院\n民事判决书\n（2024）浙0000民初1号\n原告：王某。\n被告：李某。\n诉讼请求：支付货款{amount}元。\n经审理查明，双方存在买卖关系。\n本院认为，被告应当付款。\n判决如下：被告支付货款{amount}元。\n"""


class LegalManifestTests(unittest.TestCase):
    def test_same_filename_with_changed_content_is_reprocessed(self):
        """测试目标：验证同名原始文件正文变化后不会沿用旧案件身份。
        准备数据：在临时 raw 写入文件，解析一次后改正文再解析。
        调用函数：两次调用 clean_directory 并读取结果。
        预期结果：两次 sha256 和 case_id 不同，manifest 跟随新内容。
        该断言保护的行为：增量制作数据时不能仅凭文件名错误跳过已更新案例。"""

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "raw"
            raw.mkdir()
            source = raw / "same.md"
            clean = root / "clean.jsonl"
            manifest = root / "manifest.jsonl"
            source.write_text(DOCUMENT_TEMPLATE.format(amount=100), encoding="utf-8")
            first = clean_directory(raw, clean, manifest_output=manifest)[0]
            source.write_text(DOCUMENT_TEMPLATE.format(amount=200), encoding="utf-8")
            second = clean_directory(raw, clean, manifest_output=manifest)[0]
            self.assertNotEqual(first["source"]["sha256"], second["source"]["sha256"])
            self.assertNotEqual(first["case_id"], second["case_id"])
            rows = read_jsonl(manifest)
            self.assertEqual(rows[0]["sha256"], second["source"]["sha256"])
            self.assertEqual(rows[0]["source_file"], "same.md")


if __name__ == "__main__":
    unittest.main()
