"""法律项目中文注释与数据目录 README 规范测试。

被测范围：core、methodology、tests 下的法律项目 Python 文件，以及法律数据、Prompt、Schema、Taxonomy、结果目录 README。
风险：拆分后法律仓库仍出现空泛 docstring、旧外部项目描述或缺少字段说明。
测试使用 AST 和文本读取，不导入业务模块、不调用真实模型、不写正式数据。
失败通常意味着代码注释或学习文档没有随项目边界一起更新。
"""

import ast
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_ROOTS = [PROJECT_ROOT / "core", PROJECT_ROOT / "methodology", PROJECT_ROOT / "tests"]
README_DIRS = [
    PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "data",
    PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "data" / "raw",
    PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "data" / "raw_selected_50",
    PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "data" / "parsed",
    PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "data" / "cleaned",
    PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "data" / "drafts",
    PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "data" / "manifests",
    PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "data" / "releases",
    PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "prompts",
    PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "schemas",
    PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "taxonomy",
    PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "results",
]


def has_chinese(text):
    """判断文本中是否存在中文字符。"""
    return any("\u4e00" <= char <= "\u9fff" for char in text)


class LegalDocumentationTests(unittest.TestCase):
    """保护法律项目代码注释和数据目录说明。"""

    def test_python_files_have_chinese_module_and_function_docs(self):
        """测试目标：确认法律项目每个 Python 文件和函数都有中文 docstring。

        准备数据：遍历 core、methodology、tests 的 Python 源码并解析 AST。
        调用函数：检查模块和每个函数/方法的说明文字。
        预期结果：所有说明包含中文，不使用单一空泛模板。
        该断言保护的行为：后续维护者可以理解法律数据在函数前后的变化。
        """
        generic = {"验证一个预期行为", "执行一个预期行为", "辅助函数"}
        for root in CODE_ROOTS:
            for path in root.rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                tree = ast.parse(path.read_text(encoding="utf-8"))
                module_doc = ast.get_docstring(tree) or ""
                self.assertTrue(has_chinese(module_doc), str(path))
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        doc = ast.get_docstring(node) or ""
                        self.assertTrue(has_chinese(doc), f"{path}:{node.name}")
                        self.assertFalse(doc.strip() in generic, f"{path}:{node.name}")

    def test_legal_readmes_exist_and_describe_fields(self):
        """测试目标：确认法律数据链路各目录都有可阅读的 README。

        准备数据：遍历 raw、parsed、cleaned、drafts、manifests、releases、Prompt、Schema、Taxonomy 和 results。
        调用函数：读取每个目录 README 并检查关键中文字段。
        预期结果：README 存在、非空，且总说明中出现 full_text、source_quote、validation 和 case_id。
        该断言保护的行为：原始数据和 JSONL 离开代码后仍能被人工解释。
        """
        all_text = []
        for directory in README_DIRS:
            readme = directory / "README.md"
            self.assertTrue(readme.is_file(), str(readme))
            text = readme.read_text(encoding="utf-8")
            self.assertTrue(has_chinese(text), str(readme))
            all_text.append(text)
        merged = "\n".join(all_text)
        for field in ("full_text", "source_quote", "validation", "case_id"):
            self.assertIn(field, merged)

    def test_legal_source_has_no_external_business_dependency(self):
        """测试目标：确认法律项目生产代码不导入外部 C-Eval/LLM-as-Judge 业务包。

        准备数据：读取 core 和 methodology 下的法律 Python 源码。
        调用函数：搜索旧教学业务包名、外部项目名和外部路径常量。
        预期结果：法律源码不出现旧 ceval/pairwise 业务依赖或外部项目路径。
        该断言保护的行为：法律项目可以在没有外部项目目录时独立运行。
        """
        forbidden = (
            "methodology.01_造Benchmark.ceval", "methodology.03_当裁判.pairwise",
            "CEVAL_", "PAIRWISE_", "C:\\CEval-LLMJudge",
        )
        for root in (PROJECT_ROOT / "core", PROJECT_ROOT / "methodology"):
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                for word in forbidden:
                    self.assertNotIn(word, text, f"{path} contains {word}")


if __name__ == "__main__":
    unittest.main()
