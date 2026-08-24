"""法律真实案例 Benchmark 包入口。

本包覆盖 raw 判决书无损解析、结构化提取、候选题生成、人工审核后组装、验证、评测和评分。
数据按 raw、parsed、cleaned、drafts、releases 生命周期隔离；包初始化不读写文件、不调用模型。"""