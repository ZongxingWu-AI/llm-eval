"""法律项目中文注释、批次目录和文档契约测试。"""

import ast
import importlib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BATCH_ROOT = PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "data" / "datasets" / "legal_20260827_001"
CODE_ROOTS = [PROJECT_ROOT / "core", PROJECT_ROOT / "methodology", PROJECT_ROOT / "tests"]
README_DIRS = [
    PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "data",
    BATCH_ROOT,
    BATCH_ROOT / "raw",
    BATCH_ROOT / "clean",
    BATCH_ROOT / "extract",
    BATCH_ROOT / "manifests",
    BATCH_ROOT / "drafts",
    BATCH_ROOT / "releases",
    PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "prompts",
    PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "schemas",
    PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "taxonomy",
    PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "results",
]


def has_chinese(text):
    """判断文本中是否存在中文字符。"""
    return any("\u4e00" <= char <= "\u9fff" for char in text)


class LegalDocumentationTests(unittest.TestCase):
    """保护法律项目代码注释和批次数据目录说明。"""

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

        准备数据：遍历批次 raw、clean、extract、manifests、drafts、releases 以及公共说明目录。
        调用函数：读取每个目录 README 并检查关键字段。
        预期结果：README 存在、非空，且总说明中出现 full_text、source_quote、validation 和 case_id。
        该断言保护的行为：原始数据和 JSONL 离开代码后仍可被人工解释。
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

    def test_readmes_document_batch_and_stage_naming(self):
        """测试目标：确认文档描述按批次组织、按阶段命名且不编码案例数量。

        准备数据：读取项目和当前批次的 README。
        调用函数：检查批次目录、阶段目录、伴生文件和显式路径约定。
        预期结果：文档包含 dataset_id、clean、extract、metadata 和 errors 等说明，不再依赖旧目录。
        该断言保护的行为：新增数据集时可以复用同一套命令而不误写当前批次。
        """
        paths = [PROJECT_ROOT / "README.md", PROJECT_ROOT / "methodology" / "README.md", PROJECT_ROOT / "methodology" / "01_造Benchmark" / "README.md", PROJECT_ROOT / "methodology" / "01_造Benchmark" / "module_map.md", PROJECT_ROOT / "methodology" / "02_构建题集" / "module_map.md", PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "data" / "README.md", BATCH_ROOT / "README.md"]
        paths.extend(directory / "README.md" for directory in README_DIRS if directory != PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal" / "data")
        merged = "\n".join(path.read_text(encoding="utf-8") for path in paths if path.is_file())
        for phrase in ("data/datasets/<dataset_id>", "raw", "clean", "extract", "drafts", "releases", "legal_cases_clean.jsonl", "legal_cases_extract.jsonl", ".metadata.json", ".errors.jsonl", "case_id", "source.sha256"):
            self.assertIn(phrase, merged)
        self.assertNotIn("raw_selected_50", merged)
        self.assertNotIn("legal_cases_parsed_selected_50", merged)
        self.assertNotIn("legal_cases_extracted_selected_50", merged)
        self.assertNotIn("cleaned/", merged)

    def test_learning_compendium_uses_model_answering_before_result_scoring(self):
        """验证总学习文档不把旧阶段名称或旧顺序继续传播。"""
        path = PROJECT_ROOT / "学习文档" / "16-大模型评测方法论-从零件到整车.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn("03 模型作答", text)
        self.assertIn("04 结果评测", text)
        self.assertNotIn("03 当裁判", text)
        self.assertNotIn("04 跑项目", text)
        self.assertLess(text.find("模型作答"), text.find("结果评测"))

    def test_legal_source_has_no_external_business_dependency(self):
        """测试目标：确认法律项目生产代码不导入外部 C-Eval/LLM-as-Judge 业务包。

        准备数据：读取 core 和 methodology 下的法律 Python 源码。
        调用函数：搜索旧教学业务包名、外部项目名和外部路径常量。
        预期结果：法律源码不出现旧 ceval/pairwise 业务依赖或外部项目路径。
        该断言保护的行为：法律项目可以在没有外部项目目录时独立运行。
        """
        forbidden = ("methodology.01_造Benchmark.ceval", "methodology.03_当裁判.pairwise", "CEVAL_", "PAIRWISE_", "C:\\CEval-LLMJudge")
        for root in (PROJECT_ROOT / "core", PROJECT_ROOT / "methodology"):
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                for word in forbidden:
                    self.assertNotIn(word, text, f"{path} contains {word}")


if __name__ == "__main__":
    unittest.main()
