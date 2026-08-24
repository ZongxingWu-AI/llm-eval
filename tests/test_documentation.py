"""中文代码说明与数据目录 README 的规范测试。

被测对象：core、tracks、tools、tests 下的全部 Python 文件，以及三条评测线的重要数据目录 README。
检查风险：缺失中文模块说明、函数注释退化为模板、文件写入或模型调用副作用未说明、测试目的不清楚。
测试方式：使用 AST 读取源码并检查文档文本，README 直接读取；不导入业务模块、不调用真实模型、不写正式数据。
失败含义：新增或修改代码没有达到项目约定的学习友好度，或数据字段文档不完整。
"""

from __future__ import annotations

import ast
import re
import unittest
from collections import Counter
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

COMPLEX_FUNCTIONS = {
    "core/json_utils.py": {"_balanced_candidates", "parse_json_value"},
    "core/llm_client.py": {"call_model"},
    "tracks/ceval/evaluate.py": {"evaluate_rows", "run"},
    "tracks/pairwise_judge/pairwise.py": {"judge_one"},
    "tracks/pairwise_judge/evaluate.py": {"evaluate_rows", "run"},
    "tracks/legal_benchmark/ingestion/clean.py": {"extract_parties", "split_sections", "parse_judgment", "clean_directory"},
    "tracks/legal_benchmark/extraction/extract.py": {"deterministic_extract", "extract_case", "run"},
    "tracks/legal_benchmark/generation/generate.py": {"generate_one_case", "run"},
    "tracks/legal_benchmark/dataset/build.py": {"build", "run"},
    "tracks/legal_benchmark/dataset/split.py": {"assign_case_splits"},
    "tracks/legal_benchmark/validation/validate.py": {"check_row", "validate", "run"},
    "tracks/legal_benchmark/scoring/legal_scorer.py": {"score_by_rules", "score_by_judge", "score_one"},
    "tracks/legal_benchmark/evaluation/run.py": {"evaluate_questions", "run"},
    "tools/export_excel.py": {"export_jsonl"},
}


def _has_chinese(text: str) -> bool:
    """判断说明文字是否至少含一个中文字符。

    输入：text 是模块或函数 docstring。
    输出：发现中文字符时返回 True，否则返回 False。
    副作用：只执行正则搜索，不读写文件、不调用模型。
    """

    return re.search(r"[\u4e00-\u9fff]", text) is not None


def _python_files() -> list[Path]:
    """收集规范检查覆盖的 Python 源文件。

    输入：固定扫描 CODE_ROOTS 中的 core、tracks、tools 和 tests。
    输出：返回排除 __pycache__ 后、按路径排序的 Path 列表。
    副作用：只读取目录结构，不修改文件、不调用模型。
    """

    files: list[Path] = []
    for root in CODE_ROOTS:
        for path in root.rglob("*.py"):
            if "__pycache__" not in path.parts:
                files.append(path)
    files.sort()
    return files


def _relative_path(path: Path) -> str:
    """把绝对源码路径转换为跨平台稳定的项目相对路径。

    输入：path 是 PROJECT_ROOT 下的 Python 文件。
    输出：返回使用正斜杠的相对路径字符串。
    副作用：只计算路径，不读写文件、不调用模型。
    """

    return path.relative_to(PROJECT_ROOT).as_posix()


def _function_source(source: str, node: ast.AST) -> str:
    """取得 AST 函数节点对应的源码，供副作用规则检查。

    输入：source 是完整文件文本；node 是函数或异步函数节点。
    输出：返回该函数源码片段；无法定位时返回空字符串。
    副作用：只处理内存，不写文件、不调用模型。
    """

    return ast.get_source_segment(source, node) or ""


class DocumentationTests(unittest.TestCase):
    """验证中文代码说明、测试说明和数据字段 README 不会退化。"""

    def test_every_python_file_has_chinese_module_docstring(self):
        """测试目标：确认检查范围内每个 Python 文件都有中文模块级说明。
        准备数据：遍历 core、tracks、tools、tests 下的全部 Python 文件。
        调用函数：用 ast.parse 和 ast.get_docstring 读取模块说明。
        预期结果：缺失中文说明的文件列表为空。
        该断言保护的行为：初学者打开任意代码文件都能先理解其位置、输入、输出和副作用。
        """

        missing: list[str] = []
        for path in _python_files():
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            docstring = ast.get_docstring(tree) or ""
            if not _has_chinese(docstring):
                missing.append(_relative_path(path))
        self.assertEqual([], missing, "缺少中文模块说明：" + ", ".join(missing))

    def test_every_function_has_chinese_docstring(self):
        """测试目标：确认普通函数、私有辅助函数、main 和测试方法都有中文说明。
        准备数据：解析所有 Python 文件的 AST 函数节点。
        调用函数：对每个节点读取 ast.get_docstring 并检查中文字符。
        预期结果：缺少中文函数说明的节点列表为空。
        该断言保护的行为：后续新增函数不能只依赖函数名猜测用途。
        """

        missing: list[str] = []
        for path in _python_files():
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                docstring = ast.get_docstring(node) or ""
                if not _has_chinese(docstring):
                    missing.append(f"{_relative_path(path)}:{node.name}")
        self.assertEqual([], missing, "缺少中文函数说明：" + ", ".join(missing))

    def test_module_and_function_docstrings_reject_generic_templates(self):
        """测试目标：识别曾经批量生成但没有真实信息的模块和函数模板。
        准备数据：用字符串片段拼接旧模板标记，避免本测试说明自身被误判。
        调用函数：扫描模块及函数 docstring 是否包含任一空泛标记。
        预期结果：问题列表为空。
        该断言保护的行为：注释必须描述具体数据和流程，不能只为通过“存在 docstring”检查。
        """

        generic_markers = (
            "本文件属于" + "三条评测线" + "或公共工具层",
            "本文件承接上游" + "输入",
            "参数来自上游" + "函数",
            "完成当前模块中的一个" + "处理步骤",
            "准备该测试所需的" + "最小字典",
            "对应的生产" + "函数",
            "输出字段符合当前" + " schema",
            "保护该" + "生产函数" + "的接口",
        )
        problems: list[str] = []
        for path in _python_files():
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            module_doc = ast.get_docstring(tree) or ""
            for marker in generic_markers:
                if marker in module_doc:
                    problems.append(f"{_relative_path(path)}:<module>")
                    break
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                function_doc = ast.get_docstring(node) or ""
                for marker in generic_markers:
                    if marker in function_doc:
                        problems.append(f"{_relative_path(path)}:{node.name}")
                        break
        self.assertEqual([], problems, "存在模板式空泛说明：" + ", ".join(problems))

    def test_production_functions_describe_input_output_and_side_effects(self):
        """测试目标：确认生产函数明确说明输入、输出和副作用。
        准备数据：选择 core、tracks、tools 下的函数，排除 tests。
        调用函数：检查每个函数 docstring 的三个语义标题。
        预期结果：没有函数缺少“输入、输出、副作用”中的任一项。
        该断言保护的行为：读者能判断调用函数前后数据形态以及是否会读写文件或调用模型。
        """

        problems: list[str] = []
        for path in _python_files():
            relative = _relative_path(path)
            if relative.startswith("tests/"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                docstring = ast.get_docstring(node) or ""
                missing_labels: list[str] = []
                for label in ("输入：", "输出：", "副作用："):
                    if label not in docstring:
                        missing_labels.append(label)
                if missing_labels:
                    labels = "/".join(missing_labels)
                    problems.append(f"{relative}:{node.name} 缺少 {labels}")
        self.assertEqual([], problems, "生产函数说明不完整：" + "; ".join(problems))

    def test_run_and_main_docstrings_explain_concrete_flow(self):
        """测试目标：确认 CLI main 和批处理 run 写清参数入口、输出位置及失败行为。
        准备数据：收集生产代码中名为 run 或 main 的函数。
        调用函数：检查说明中是否包含用途、输入、输出、副作用和异常处理。
        预期结果：所有入口函数均包含五类信息。
        该断言保护的行为：读者能从入口注释理解命令行参数如何进入业务流程以及失败如何退出。
        """

        required = ("用途：", "输入：", "输出：", "副作用：", "异常或失败处理：")
        problems: list[str] = []
        for path in _python_files():
            relative = _relative_path(path)
            if relative.startswith("tests/"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name not in {"run", "main"}:
                    continue
                docstring = ast.get_docstring(node) or ""
                for label in required:
                    if label not in docstring:
                        problems.append(f"{relative}:{node.name} 缺少 {label}")
        self.assertEqual([], problems, "run/main 说明不完整：" + "; ".join(problems))

    def test_file_writers_and_model_callers_disclose_side_effects(self):
        """测试目标：确认源码中真实存在的文件写入和模型调用在注释里明确披露。
        准备数据：提取每个生产函数源码并查找写文件调用和 call_model。
        调用函数：对命中函数检查 docstring 中的“写/覆盖/创建”和“调用模型”说明。
        预期结果：没有未说明关键副作用的函数。
        该断言保护的行为：调用者不会误把有磁盘或网络副作用的函数当成纯函数。
        """

        write_markers = ("write_jsonl(", ".write_text(", ".mkdir(", ".save(")
        problems: list[str] = []
        for path in _python_files():
            relative = _relative_path(path)
            if relative.startswith("tests/"):
                continue
            source = path.read_text(encoding="utf-8-sig")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                code = _function_source(source, node)
                docstring = ast.get_docstring(node) or ""
                writes_file = False
                for marker in write_markers:
                    if marker in code:
                        writes_file = True
                        break
                if writes_file and not any(word in docstring for word in ("写", "覆盖", "创建")):
                    problems.append(f"{relative}:{node.name} 未说明文件写入")
                calls_model = "call_model(" in code or node.name == "call_model"
                if calls_model and "调用模型" not in docstring:
                    problems.append(f"{relative}:{node.name} 未说明调用模型")
        self.assertEqual([], problems, "副作用说明不完整：" + "; ".join(problems))

    def test_complex_functions_explain_data_changes(self):
        """测试目标：确认核心解析、评分、构建和评测函数解释运行前后数据变化。
        准备数据：使用 COMPLEX_FUNCTIONS 列出的高认知负担函数集合。
        调用函数：定位函数并检查“运行前数据形态”和“运行后数据变化”。
        预期结果：所有登记函数均存在且包含两个说明标题。
        该断言保护的行为：复杂流程必须给出输入到输出的阅读线索，而不是只写一句用途。
        """

        problems: list[str] = []
        for relative, names in COMPLEX_FUNCTIONS.items():
            path = PROJECT_ROOT / relative
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            found: set[str] = set()
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name not in names:
                    continue
                found.add(node.name)
                docstring = ast.get_docstring(node) or ""
                for label in ("运行前数据形态：", "运行后数据变化："):
                    if label not in docstring:
                        problems.append(f"{relative}:{node.name} 缺少 {label}")
            for name in names:
                if name not in found:
                    problems.append(f"{relative}:{name} 不存在")
        self.assertEqual([], problems, "核心函数数据变化说明不完整：" + "; ".join(problems))

    def test_test_methods_explain_target_setup_call_expectation_and_risk(self):
        """测试目标：确认每个 test_* 方法说明测试对象、准备、调用、预期和保护风险。
        准备数据：收集 tests 下全部测试方法 docstring。
        调用函数：检查五个固定语义标题，并统计完全重复的说明。
        预期结果：没有缺标题的测试，且每个测试说明内容唯一。
        该断言保护的行为：测试文件可作为业务行为说明书，而不是只有断言代码。
        """

        required = ("测试目标：", "准备数据：", "调用函数：", "预期结果：", "该断言保护的行为：")
        problems: list[str] = []
        test_docs: list[str] = []
        for path in _python_files():
            relative = _relative_path(path)
            if not relative.startswith("tests/"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not node.name.startswith("test_"):
                    continue
                docstring = ast.get_docstring(node) or ""
                test_docs.append(docstring)
                for label in required:
                    if label not in docstring:
                        problems.append(f"{relative}:{node.name} 缺少 {label}")
        duplicates = Counter(test_docs)
        for docstring, count in duplicates.items():
            if docstring and count > 1:
                first_line = docstring.splitlines()[0]
                problems.append(f"测试说明重复 {count} 次：{first_line}")
        self.assertEqual([], problems, "测试方法说明不完整：" + "; ".join(problems))

    def test_production_code_avoids_comprehensions_and_lambda(self):
        """测试目标：确认生产代码没有重新引入推导式、生成器表达式或 lambda。
        准备数据：解析 core、tracks、tools 下全部 Python 文件的抽象语法树。
        调用函数：遍历 AST 并收集 ListComp、SetComp、DictComp、GeneratorExp 和 Lambda 节点。
        预期结果：复杂语法节点列表为空，数据处理过程使用普通循环和命名中间变量。
        该断言保护的行为：项目代码持续适合初学者逐步阅读，而不是只在本次重构中临时简化。
        """

        production_roots = (
            PROJECT_ROOT / "core",
            PROJECT_ROOT / "tracks",
            PROJECT_ROOT / "tools",
        )
        complex_node_types = (
            ast.ListComp,
            ast.SetComp,
            ast.DictComp,
            ast.GeneratorExp,
            ast.Lambda,
        )
        problems: list[str] = []
        for root in production_roots:
            for path in sorted(root.rglob("*.py")):
                tree = ast.parse(path.read_text(encoding="utf-8-sig"))
                relative = _relative_path(path)
                for node in ast.walk(tree):
                    if isinstance(node, complex_node_types):
                        node_name = type(node).__name__
                        problems.append(f"{relative}:{node.lineno} 使用 {node_name}")
        self.assertEqual([], problems, "生产代码仍有复杂语法：" + "; ".join(problems))

    def test_required_readmes_and_field_names_exist(self):
        """测试目标：确认关键数据、Prompt、Schema、Taxonomy 和结果目录都有字段级 README。
        准备数据：README_REQUIREMENTS 为每个目录列出必须解释的代表字段。
        调用函数：逐个读取 README 并搜索字段名。
        预期结果：所有文件存在且必需字段全部出现。
        该断言保护的行为：读者能独立理解 JSON/JSONL 文件含义、上下游和 Git 提交策略。
        """

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

