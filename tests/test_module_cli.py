"""法律项目 CLI 和模块导入测试。

被测对象：法律 Benchmark 的六个入口以及 core 公共层。
风险：前两条线迁移后旧入口仍被误写入法律项目，或 --help 触发模型和文件副作用。
测试只导入模块并运行 --help，不调用真实模型、不重新解析案例、不生成题目。
失败通常意味着法律仓库边界或命令入口没有完成收缩。
"""

import importlib
import subprocess
import sys
import unittest

MODULES = [
    "methodology.01_造Benchmark.legal.ingestion.clean",
    "methodology.01_造Benchmark.legal.extraction.extract",
    "methodology.02_构建题集.legal.generation.generate",
    "methodology.02_构建题集.legal.dataset.build",
    "methodology.02_构建题集.legal.validation.validate",
    "methodology.04_跑项目.legal.evaluation.run",
]


class LegalModuleCliTests(unittest.TestCase):
    """保护法律项目自身的导入和命令行入口。"""

    def test_legal_modules_import(self):
        """测试目标：确认六个法律入口可导入且不依赖外部项目业务包。

        准备数据：准备法律模块的完整包名列表。
        调用函数：逐个 importlib.import_module。
        预期结果：全部导入成功，不读取模型配置。
        该断言保护的行为：C-Eval 与 LLM-as-Judge 拆出后法律代码仍可独立学习运行。
        """
        for module_name in MODULES:
            with self.subTest(module=module_name):
                importlib.import_module(module_name)

    def test_legal_help_commands_exit_zero(self):
        """测试目标：确认法律六个 CLI 的 --help 退出码为 0。

        准备数据：不给输入文件和 API key，只传 --help。
        调用函数：使用当前 Python 启动每个法律模块。
        预期结果：进程成功并输出 usage 或帮助文本。
        该断言保护的行为：命令入口不会在参数解析前执行真实评测副作用。
        """
        for module_name in MODULES:
            with self.subTest(module=module_name):
                completed = subprocess.run(
                    [sys.executable, "-m", module_name, "--help"],
                    capture_output=True, text=True, timeout=30,
                )
                output = completed.stdout + completed.stderr
                self.assertEqual(completed.returncode, 0, output)
                self.assertTrue("usage" in output.lower() or "帮助" in output, output)


if __name__ == "__main__":
    unittest.main()
