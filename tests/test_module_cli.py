"""测试模块：tests/test_module_cli.py。

本文件验证项目中的一个具体行为或模块边界。测试输入通常是内存中的最小样例，测试输出是断言结果，不调用真实模型 API。

项目位置：tests/test_module_cli.py。
主要用途：项目测试模块，验证公共基础层和三条评测线的行为、数据隔离与文档规范。
输入：输入来自测试夹具、临时目录和项目模块。
输出：输出为测试断言结果，不产生正式评测数据。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：通常只创建临时文件或调用测试替身，不调用真实模型 API。
"""

import importlib
import subprocess
import sys
import unittest

MODULES = [
    "core.prompt_loader",
    "core.json_utils",
    "tracks.ceval.fetch",

    "tracks.ceval.fetch",
    "tracks.ceval.evaluate",
    "tracks.pairwise_judge.generate_answers",
    "tracks.pairwise_judge.evaluate",
    "tracks.legal_benchmark.ingestion.clean",
    "tracks.legal_benchmark.extraction.extract",
    "tracks.legal_benchmark.generation.generate",
    "tracks.legal_benchmark.dataset.build",
    "tracks.legal_benchmark.validation.validate",
    "tracks.legal_benchmark.evaluation.run",
    "tools.export_excel",
]

CLI_MODULES = [
    "tracks.ceval.fetch",
    "tracks.ceval.evaluate",
    "tracks.pairwise_judge.generate_answers",
    "tracks.pairwise_judge.evaluate",
    "tracks.legal_benchmark.ingestion.clean",
    "tracks.legal_benchmark.extraction.extract",
    "tracks.legal_benchmark.generation.generate",
    "tracks.legal_benchmark.dataset.build",
    "tracks.legal_benchmark.validation.validate",
    "tracks.legal_benchmark.evaluation.run",
    "tools.export_excel",
]


class ModuleAndCliTests(unittest.TestCase):
    def test_all_tracks_import_without_legacy_packages(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        for module in MODULES:
            with self.subTest(module=module):
                importlib.import_module(module)

    def test_all_documented_clis_support_help(self):
        """验证一个预期行为，失败时应优先检查断言对应的实现边界。

参数：self。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

        for module in CLI_MODULES:
            with self.subTest(module=module):
                completed = subprocess.run(
                    [sys.executable, "-m", module, "--help"],
                    text=True,
                    capture_output=True,
                    timeout=30,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn("--help", completed.stdout)


if __name__ == "__main__":
    unittest.main()
