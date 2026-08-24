"""三条评测线的顶层包入口。

本包下分别包含 ceval、pairwise_judge 和 legal_benchmark，公共能力从 core 导入。
包初始化不迁移数据、不创建结果目录、不调用模型，实际流程均通过 python -m 子模块启动。"""