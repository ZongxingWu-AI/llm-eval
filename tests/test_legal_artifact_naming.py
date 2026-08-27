"""法律 Benchmark 产物命名和显式路径契约测试。"""

import importlib
import inspect
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGAL_ROOT = PROJECT_ROOT / "methodology" / "01_造Benchmark" / "legal"


class LegalArtifactNamingTests(unittest.TestCase):
    """保护法律 Benchmark 按批次、阶段和实体命名的契约。"""

    def test_paths_expose_project_roots_but_not_batch_defaults(self):
        """测试目标：paths.py 只暴露项目级路径，不绑定当前数据批次。

        准备数据：导入法律路径模块并读取源代码。
        调用函数：检查 DATASETS_ROOT 和旧批次字样。
        预期结果：存在批次根目录常量，不存在 selected_50 等具体输入输出常量。
        该断言保护的行为：后续批次可以只替换命令行路径而不用改代码。
        """
        paths = importlib.import_module("methodology.01_造Benchmark.legal.paths")
        self.assertEqual(paths.DATASETS_ROOT, paths.DATA_ROOT / "datasets")
        source = (LEGAL_ROOT / "paths.py").read_text(encoding="utf-8")
        self.assertNotIn("raw_selected_50", source)
        self.assertNotIn("selected_50", source)

    def test_stage_functions_require_dataset_paths(self):
        """测试目标：各阶段 Python API 不再默认使用某个数据集的路径。

        准备数据：导入 clean、extract、generation、build、validation 和 evaluation。
        调用函数：检查 run/clean_directory 的签名默认值。
        预期结果：输入输出数据路径均为必填参数；只有试跑数量、开关和运行目录可以有默认值。
        该断言保护的行为：显式路径避免把新数据误写进旧批次。
        """
        modules = {
            "clean": importlib.import_module("methodology.01_造Benchmark.legal.ingestion.clean"),
            "extract": importlib.import_module("methodology.01_造Benchmark.legal.extraction.extract"),
            "generation": importlib.import_module("methodology.02_构建题集.legal.generation.generate"),
            "build": importlib.import_module("methodology.02_构建题集.legal.dataset.build"),
            "validation": importlib.import_module("methodology.02_构建题集.legal.validation.validate"),
            "evaluation": importlib.import_module("methodology.04_跑项目.legal.evaluation.run"),
        }
        for name, function in (("clean", modules["clean"].clean_directory), ("extract", modules["extract"].run), ("generation", modules["generation"].run), ("build", modules["build"].run), ("validation", modules["validation"].run), ("evaluation", modules["evaluation"].run)):
            with self.subTest(stage=name):
                for parameter in inspect.signature(function).parameters.values():
                    if parameter.name in {"raw_dir", "input_path", "output_path", "manifest_output", "manifest_path", "cases_path"}:
                        self.assertIs(parameter.default, inspect.Parameter.empty, f"{name}.{parameter.name}")

    def test_cli_requires_data_paths(self):
        """测试目标：六个阶段 CLI 都把具体数据路径作为显式参数。

        准备数据：读取六个入口模块的源码。
        调用函数：检查 argparse 对输入输出参数设置 required=True。
        预期结果：代码不再包含数据集专属默认路径。
        该断言保护的行为：--max-items 只能限制试跑数量，不能决定正式产物落点。
        """
        modules = [
            "methodology/01_造Benchmark/legal/ingestion/clean.py",
            "methodology/01_造Benchmark/legal/extraction/extract.py",
            "methodology/02_构建题集/legal/generation/generate.py",
            "methodology/02_构建题集/legal/dataset/build.py",
            "methodology/02_构建题集/legal/validation/validate.py",
            "methodology/04_跑项目/legal/evaluation/run.py",
        ]
        for rel in modules:
            source = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("selected_50", source, rel)
            self.assertNotIn("cleaned/", source, rel)
        clean = (PROJECT_ROOT / modules[0]).read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--raw-dir", "--input", required=True', clean)
        self.assertIn('parser.add_argument("--output", required=True', clean)
        self.assertIn('parser.add_argument("--manifest-output", required=True', clean)

    def test_evaluation_artifact_names_are_semantic(self):
        """测试目标：评测运行目录内的结果文件使用领域和实体命名。

        准备数据：读取 evaluation.run 的模块源码。
        调用函数：检查结果文件名称文本。
        预期结果：结果、错误、报告和 Excel 文件均带有法律评测语义。
        该断言保护的行为：独立运行目录中的文件脱离目录后仍可理解。
        """
        source = (PROJECT_ROOT / "methodology" / "04_跑项目" / "legal" / "evaluation" / "run.py").read_text(encoding="utf-8")
        for name in ("legal_evaluation_results.jsonl", "legal_evaluation_errors.jsonl", "legal_evaluation_report.md", "legal_evaluation_results.xlsx"):
            self.assertIn(name, source)

    def test_no_deprecated_batch_names_remain_in_project_text(self):
        """测试目标：项目文本不再引用已废弃的批次目录和阶段产物名称。

        准备数据：遍历生产代码、测试、README 和教学文档，排除正式数据内容。
        调用函数：搜索旧批次名称和旧阶段目录。
        预期结果：旧名称不会成为后续运行的隐性入口。
        该断言保护的行为：所有新数据都通过 dataset_id 隔离。
        """
        forbidden = ("raw_selected_50", "legal_cases_parsed_selected_50", "legal_cases_extracted_selected_50", "legal_questions_draft_selected_50", "data/cleaned", "data\\cleaned")
        roots = (PROJECT_ROOT / "core", PROJECT_ROOT / "methodology", PROJECT_ROOT / "学习文档", PROJECT_ROOT / ".gitignore")
        for root in roots:
            paths = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts and "data" not in p.parts]
            for path in paths:
                if path == Path(__file__):
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                for word in forbidden:
                    self.assertNotIn(word, text, f"{path} still references {word}")


if __name__ == "__main__":
    unittest.main()

