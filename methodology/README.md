# 法律 Benchmark 教学总索引

当前仓库只保留法律真实案例 Benchmark。四个目录对应教学文档中的四个环节：

```text
造 Benchmark → 构建题集 → 当裁判 → 跑项目
```

法律线的数据流是：

```text
raw 判决书 → clean → extract → drafts → releases → validation → evaluation
```

## 四个目录

- `01_造Benchmark`：按批次管理原始判决书，进行无损解析和法律信息提取。
- `02_构建题集`：生成候选题、人工审核、组装 release、案件级划分和校验。
- `03_当裁判`：选择规则/Rubric 评分方法，输出 PASS/REVIEW/REJECT。
- `04_跑项目`：批量运行法律题集，保存结果、报告和运行元数据。

## 批次数据

正式数据统一位于 `methodology/01_造Benchmark/legal/data/datasets/<dataset_id>/`。每个批次内部使用 `raw/`、`clean/`、`extract/`、`manifests/`、`drafts/` 和 `releases/`，具体文件路径通过命令行传递。

公共基础层位于 `core`，由四个法律环节共同调用，不属于某一个环节。
