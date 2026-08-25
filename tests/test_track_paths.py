"""法律项目路径边界测试。

被测模块：core.project_paths 和法律业务 paths 模块。
风险：法律项目残留 C-Eval、Pairwise 或外部项目路径常量，导致结果目录交叉污染。
测试只读取 Path 常量，不创建目录、不调用模型、不改动法律数据。
"""

import importlib
import unittest

from core import project_paths

legal_paths = importlib.import_module("methodology.01_造Benchmark.legal.paths")


class LegalTrackPathTests(unittest.TestCase):
    """保护法律项目的结果目录和公共常量边界。"""

    def test_only_legal_path_constants_remain(self):
        """测试目标：确认公共路径层只导出法律项目需要的路径。

        准备数据：读取 core.project_paths 的公开名称和值。
        调用函数：检查不存在 CEVAL、PAIRWISE 或外部项目路径常量。
        预期结果：保留四个教学目录和 LEGAL_* 路径，法律结果位于法律目录。
        该断言保护的行为：法律仓库可在没有外部项目的情况下独立运行。
        """
        names = vars(project_paths)
        self.assertFalse(any(name.startswith("CEVAL_") for name in names))
        self.assertFalse(any(name.startswith("PAIRWISE_") for name in names))
        self.assertIn("LEGAL_RESULTS_ROOT", names)
        self.assertEqual(legal_paths.RESULTS_ROOT.resolve(), project_paths.LEGAL_RESULTS_ROOT.resolve())
        self.assertIn("legal", str(legal_paths.RESULTS_ROOT).lower())
        self.assertNotIn("CEval-LLMJudge", str(project_paths.PROJECT_ROOT))


if __name__ == "__main__":
    unittest.main()
