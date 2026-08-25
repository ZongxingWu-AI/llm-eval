# 精选 50 案原始案例目录

## 1. 目录用途

保存已经人工筛选、准备进入法律 Benchmark 第一版流程的约 50 份民事一审判决书。它是 raw 原始案例的一个“精选输入集”，不改变原文内容。

## 2. 数据来源

文件来自本地人工筛选结果。文件名中的前缀表示人工确认的一级方向，例如“合同纠纷__”应映射为“合同、准合同纠纷”。来源网址、SHA-256、获取时间和审核状态仍通过 data/manifests/ 记录。

## 3. 文件命名规则

一案一文件，支持 .md 和 .txt。推荐格式：

~~~text
合同纠纷__（2024）浙0483民初5218号.md
~~~

双下划线前面的分类是人工确认标签；双下划线后面保留原始案号。不要通过文件名截断正文。

## 4. 文件内容说明

每个文件保存完整判决书原文。清洗程序会读取全文，生成 parsed 案件对象；不会因为文件放在精选目录而丢弃诉讼请求、事实、法院说理、判决主文、法条、金额或日期。

## 5. 上游和下游

~~~text
本目录原始判决书
    ↓ methodology.01_造Benchmark.legal.ingestion.clean
methodology/01_造Benchmark/legal/data/parsed/
    ↓ methodology.01_造Benchmark.legal.extraction.extract
methodology/01_造Benchmark/legal/data/cleaned/
~~~

## 6. 是否提交 Git

除本 README 外，本目录中的判决书全部保持本地使用并由 .gitignore 忽略。未经来源、隐私、脱敏和质量审核，不得进入公开 release。


