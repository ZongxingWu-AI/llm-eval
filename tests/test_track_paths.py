"""三条评测线路径隔离测试。

被测模块：ceval、pairwise_judge、legal_benchmark 的 paths 常量。只比较解析后的 Path，不创建目录、不调用模型。
失败表示不同评测线可能写入同一 results 根目录并相互污染。"""

import unittest

from tracks.ceval.paths import RESULTS_ROOT as CEVAL_RESULTS
from tracks.legal_benchmark.paths import RESULTS_ROOT as LEGAL_RESULTS
from tracks.pairwise_judge.paths import RESULTS_ROOT as PAIRWISE_RESULTS

from tracks.pairwise_judge.paths import RESULTS_ROOT as PAIRWISE_RESULTS


class TrackPathIsolationTests(unittest.TestCase):
    def test_each_track_has_its_own_results_root(self):
        """测试目标：验证三条评测线的 RESULTS_ROOT 两两不同且位于各自目录。
        准备数据：导入三个 paths 模块的结果根路径。
        调用函数：解析并比较三个 Path。
        预期结果：集合长度为 3，路径分别包含 ceval、pairwise_judge、legal_benchmark。
        该断言保护的行为：任何运行结果都不会写进另一条评测线。"""

        roots = {CEVAL_RESULTS.resolve(), PAIRWISE_RESULTS.resolve(), LEGAL_RESULTS.resolve()}
        self.assertEqual(len(roots), 3)
        self.assertTrue(str(CEVAL_RESULTS).endswith("tracks\\ceval\\results"))
        self.assertTrue(str(PAIRWISE_RESULTS).endswith("tracks\\pairwise_judge\\results"))
        self.assertTrue(str(LEGAL_RESULTS).endswith("tracks\\legal_benchmark\\results"))


if __name__ == "__main__":
    unittest.main()
