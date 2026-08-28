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
        """确认公共路径只暴露项目级目录，不绑定某个具体数据批次。"""
        paths = importlib.import_module("methodology.01_造Benchmark.legal.paths")
        self.assertEqual(paths.DATASETS_ROOT, paths.DATA_ROOT / "datasets")
        source = (LEGAL_ROOT / "paths.py").read_text(encoding="utf-8")
        self.assertNotIn("raw_selected_50", source)
        self.assertNotIn("selected_50", source)

    def test_stage_functions_require_dataset_paths(self):
        """确认各阶段 API 的题集、回答和输出路径均需显式传入。"""
        modules = {
            "clean": importlib.import_module("methodology.01_造Benchmark.legal.ingestion.clean"),
            "extract": importlib.import_module("methodology.01_造Benchmark.legal.extraction.extract"),
            "generation": importlib.import_module("methodology.02_构建题集.legal.generation.generate"),
            "build": importlib.import_module("methodology.02_构建题集.legal.dataset.build"),
            "validation": importlib.import_module("methodology.02_构建题集.legal.validation.validate"),
            "answering": importlib.import_module("methodology.03_模型作答.legal.evaluation.run"),
            "scoring": importlib.import_module("methodology.04_结果评测.legal.scoring.run"),
        }
        functions = (
            ("clean", modules["clean"].clean_directory),
            ("extract", modules["extract"].run),
            ("generation", modules["generation"].run),
            ("build", modules["build"].run),
            ("validation", modules["validation"].run),
            ("answering", modules["answering"].run),
            ("scoring", modules["scoring"].run),
        )
        required_names = {"raw_dir", "input_path", "output_path", "manifest_output", "manifest_path", "cases_path", "questions_path", "outputs_path"}
        for name, function in functions:
            with self.subTest(stage=name):
                for parameter in inspect.signature(function).parameters.values():
                    if parameter.name in required_names:
                        self.assertIs(parameter.default, inspect.Parameter.empty, f"{name}.{parameter.name}")

    def test_cli_requires_data_paths(self):
        """确认六条数据阶段 CLI 都把具体输入输出路径作为显式参数。"""
        modules = [
            "methodology/01_造Benchmark/legal/ingestion/clean.py",
            "methodology/01_造Benchmark/legal/extraction/extract.py",
            "methodology/02_构建题集/legal/generation/generate.py",
            "methodology/02_构建题集/legal/dataset/build.py",
            "methodology/02_构建题集/legal/validation/validate.py",
            "methodology/03_模型作答/legal/evaluation/run.py",
            "methodology/04_结果评测/legal/scoring/run.py",
        ]
        for rel in modules:
            source = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("selected_50", source, rel)
            self.assertNotIn("cleaned/", source, rel)
        clean = (PROJECT_ROOT / modules[0]).read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--raw-dir", "--input", required=True', clean)
        self.assertIn('parser.add_argument("--output", required=True', clean)
        self.assertIn('parser.add_argument("--manifest-output", required=True', clean)
        scoring = (PROJECT_ROOT / modules[-1]).read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--questions", "--input", dest="questions", required=True', scoring)
        self.assertIn('parser.add_argument("--outputs", required=True', scoring)
        self.assertIn('parser.add_argument("--output", required=True', scoring)

    def test_evaluation_artifact_names_are_semantic(self):
        """确认 04 结果评测使用法律语义化结果、错误、报告和 Excel 文件名。"""
        source = (PROJECT_ROOT / "methodology" / "04_结果评测" / "legal" / "scoring" / "run.py").read_text(encoding="utf-8")
        for name in ("legal_evaluation_results.jsonl", "legal_evaluation_errors.jsonl", "legal_evaluation_report.md", "legal_evaluation_results.xlsx"):
            self.assertIn(name, source)

    def test_no_deprecated_batch_names_remain_in_project_text(self):
        """确认项目文本不再引用已经废弃的批次目录和阶段产物名称。"""
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
