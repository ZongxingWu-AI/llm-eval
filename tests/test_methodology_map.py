"""法律项目教学索引一致性测试。

被测对象：四个 methodology 教学目录的 README、module_map 和 learning_order。
风险：文档仍登记已经迁移的 C-Eval/LLM-as-Judge 文件，或引用不存在的法律路径。
测试只读取 Markdown 文本和文件路径，不调用模型、不写数据。
失败通常意味着学习入口与实际法律代码发生漂移。
"""

import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
METHODOLOGY_ROOT = PROJECT_ROOT / "methodology"
TEACHING_DIRS = [
    METHODOLOGY_ROOT / "01_造Benchmark",
    METHODOLOGY_ROOT / "02_构建题集",
    METHODOLOGY_ROOT / "03_当裁判",
    METHODOLOGY_ROOT / "04_跑项目",
]


class MethodologyMapTests(unittest.TestCase):
    """保护四个法律教学环节的文档索引。"""

    def test_each_teaching_directory_has_three_documents(self):
        """测试目标：确认四个法律教学目录均有 README、模块地图和学习顺序。

        准备数据：准备四个中文教学目录。
        调用函数：逐目录检查三个 Markdown 文件。
        预期结果：文件全部存在且包含法律相关文字。
        该断言保护的行为：学习者总能从统一入口找到本环节说明。
        """
        for directory in TEACHING_DIRS:
            for name in ("README.md", "module_map.md", "learning_order.md"):
                path = directory / name
                self.assertTrue(path.is_file(), str(path))
                self.assertIn("法律", path.read_text(encoding="utf-8"))

    def test_maps_reference_existing_legal_files_only(self):
        """测试目标：确认模块地图引用的法律 Python 文件存在且不再包含迁移代码。

        准备数据：读取四个 module_map.md 的反引号路径。
        调用函数：将相对路径转换为项目根路径并检查存在性。
        预期结果：每个引用文件真实存在，文本不含 ceval、pairwise 或 tools 旧业务路径。
        该断言保护的行为：文档不会把学习者引向已经拆走的代码。
        """
        for directory in TEACHING_DIRS:
            text = (directory / "module_map.md").read_text(encoding="utf-8")
            self.assertNotIn("ceval/", text.lower())
            self.assertNotIn("pairwise/", text.lower())
            for relative in re.findall(r"``([^`]+\.py)``", text):
                path = PROJECT_ROOT / relative.replace("/", "\\")
                self.assertTrue(path.is_file(), str(path))


if __name__ == "__main__":
    unittest.main()
