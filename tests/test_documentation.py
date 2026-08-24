"""文档规范测试。

本文件检查项目代码和数据目录是否遵守可读性约定：
每个 Python 文件有中文模块说明，每个函数有中文 docstring，
关键数据目录有 README，并且 README 覆盖主要 JSON 字段。

项目位置：tests/test_documentation.py。
主要用途：项目测试模块，验证公共基础层和三条评测线的行为、数据隔离与文档规范。
输入：输入来自测试夹具、临时目录和项目模块。
输出：输出为测试断言结果，不产生正式评测数据。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：通常只创建临时文件或调用测试替身，不调用真实模型 API。
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_ROOTS = (
    PROJECT_ROOT / "core",
    PROJECT_ROOT / "tracks",
    PROJECT_ROOT / "tools",
    PROJECT_ROOT / "tests",
)


README_REQUIREMENTS = {
    PROJECT_ROOT / "tracks" / "ceval" / "data" / "README.md":
        ("id", "subject", "question", "answer"),
    PROJECT_ROOT / "tracks" / "ceval" / "prompts" / "README.md":
        ("Prompt", "输入", "输出"),
    PROJECT_ROOT / "tracks" / "ceval" / "results" / "README.md":
        ("predicted_answer", "correct_answer", "latency_seconds"),
    PROJECT_ROOT / "tracks" / "pairwise_judge" / "data" / "README.md":
        ("answer_a", "answer_b", "model_a", "model_b"),
    PROJECT_ROOT / "tracks" / "pairwise_judge" / "prompts" / "README.md":
        ("question", "answer_a", "answer_b"),
    PROJECT_ROOT / "tracks" / "pairwise_judge" / "results" / "README.md":
        ("judge_winner", "position_bias", "round1_winner", "round2_winner"),
    PROJECT_ROOT / "tracks" / "legal_benchmark" / "data" / "README.md":
        ("raw", "parsed", "cleaned", "drafts", "releases"),
    PROJECT_ROOT / "tracks" / "legal_benchmark" / "data" / "raw" / "README.md":
        ("source_url", "sha256", "local_only"),
    PROJECT_ROOT / "tracks" / "legal_benchmark" / "data" / "parsed" / "README.md":
        ("full_text", "sections", "parties", "quality"),
    PROJECT_ROOT / "tracks" / "legal_benchmark" / "data" / "cleaned" / "README.md":
        ("legal_extraction", "source_section", "source_quote"),
    PROJECT_ROOT / "tracks" / "legal_benchmark" / "data" / "drafts" / "README.md":
        ("question_id", "reference_answer", "rubric", "review_status"),
    PROJECT_ROOT / "tracks" / "legal_benchmark" / "data" / "manifests" / "README.md":
        ("case_id", "sha256", "review_status", "validation_status"),
    PROJECT_ROOT / "tracks" / "legal_benchmark" / "data" / "releases" / "README.md":
        ("reference_answer", "rubric", "source_evidence"),
    PROJECT_ROOT / "tracks" / "legal_benchmark" / "prompts" / "README.md":
        ("case_sections", "source_quote", "reference_answer"),
    PROJECT_ROOT / "tracks" / "legal_benchmark" / "schemas" / "README.md":
        ("question_id", "case_id", "split", "source_evidence"),
    PROJECT_ROOT / "tracks" / "legal_benchmark" / "taxonomy" / "README.md":
        ("primary_categories", "cause_tree", "scoring_methods"),
    PROJECT_ROOT / "tracks" / "legal_benchmark" / "results" / "README.md":
        ("legal_results.jsonl", "errors.jsonl", "run_metadata.json"),
}


def _has_chinese(text: str) -> bool:
    """判断文本是否至少包含一个中文字符。"""
    return re.search(r"[\u4e00-\u9fff]", text) is not None


def _python_files() -> list[Path]:
    """收集需要检查的 Python 文件。"""
    files: list[Path] = []
    for root in CODE_ROOTS:
        files.extend(root.rglob("*.py"))
    return sorted(path for path in files if "__pycache__" not in path.parts)


class DocumentationTests(unittest.TestCase):
    """验证项目代码注释和数据目录 README 的完整性。"""

    def test_every_python_file_has_chinese_module_docstring(self):
        """每个 Python 文件都必须有中文模块说明。"""
        missing: list[str] = []
        for path in _python_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docstring = ast.get_docstring(tree) or ""
            if not _has_chinese(docstring):
                missing.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual([], missing, "缺少中文模块说明：" + ", ".join(missing))

    def test_every_function_has_chinese_docstring(self):
        """每个普通函数、异步函数和方法都必须有中文说明。"""
        missing: list[str] = []
        for path in _python_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                docstring = ast.get_docstring(node) or ""
                if not _has_chinese(docstring):
                    missing.append(f"{path.relative_to(PROJECT_ROOT)}:{node.name}")
        self.assertEqual([], missing, "缺少中文函数说明：" + ", ".join(missing))

    def test_function_docstrings_are_specific_and_not_template_text(self):
        """禁止使用没有说明真实业务的模板注释。

        该测试专门检查两类问题：一是生产函数不能只写“完成当前模块中的一个处理步骤”，
        二是测试函数不能全部复制“验证一个预期行为”。这样可以防止代码表面有注释、
        但读者仍然不知道输入输出和测试目的。
        """
        generic_markers = (
            "完成当前模块中的一个" + "处理步骤",
            "验证一个预期行为，失败时应优先检查断言对应的" + "实现边界",
            "为同一文件中的公开流程提供一个小而明确的" + "辅助步骤",
        )
        problems: list[str] = []
        for path in _python_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                docstring = ast.get_docstring(node) or ""
                if any(marker in docstring for marker in generic_markers):
                    problems.append(f"{path.relative_to(PROJECT_ROOT)}:{node.name}")
        self.assertEqual([], problems, "存在模板式空泛函数说明：" + ", ".join(problems))

    def test_required_readmes_and_field_names_exist(self):
        """每个数据相关目录都必须有字段级 README 和最小示例说明。"""
        problems: list[str] = []
        for path, fields in README_REQUIREMENTS.items():
            if not path.is_file():
                problems.append(f"缺少文件：{path.relative_to(PROJECT_ROOT)}")
                continue
            text = path.read_text(encoding="utf-8")
            for field in fields:
                if field not in text:
                    problems.append(f"{path.relative_to(PROJECT_ROOT)} 缺少字段：{field}")
        self.assertEqual([], problems, "README 不完整：" + "; ".join(problems))


if __name__ == "__main__":
    unittest.main()

