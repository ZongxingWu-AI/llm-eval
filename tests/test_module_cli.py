"""模块导入与 CLI 帮助测试。

被测对象：三条评测线的新模块路径和十一条 python -m 命令。通过 importlib 与 subprocess 检查，不调用业务 run。
不 mock 模型、不创建正式数据；--help 应在任何 API 配置缺失时仍退出 0。
失败表示迁移后仍依赖旧根目录模块，或命令入口在参数解析前执行了副作用。"""

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
        """测试目标：验证新模块都可导入且不依赖已删除的旧根目录包。
        准备数据：准备公共层和三条评测线模块名列表。
        调用函数：用 importlib.import_module 逐个导入。
        预期结果：所有导入成功。
        该断言保护的行为：模块化迁移没有遗留 runner、judge 等旧依赖。"""

        for module in MODULES:
            with self.subTest(module=module):
                importlib.import_module(module)

    def test_all_documented_clis_support_help(self):
        """测试目标：验证 README 约定的十一条 python -m 命令均支持 --help。
        准备数据：准备 CLI 模块名并使用当前 Python 启动子进程。
        调用函数：逐个执行 python -m 模块 --help。
        预期结果：每个退出码为 0 且输出帮助文本。
        该断言保护的行为：命令入口不会在参数解析前要求 API 密钥或执行真实评测。"""

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
