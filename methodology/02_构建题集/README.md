# 02 构建题集：法律问题、Golden Answer 与 Rubric

本环节把结构化案件变成候选问题，经过人工审核后组装正式题集，并进行案件级 dev/calibration/test 划分。

主要入口：``methodology/02_构建题集/legal/generation/generate.py``、
``dataset/build.py``、``dataset/split.py``、``validation/validate.py``。
候选题默认是 ``pending``，只有人工审核为 ``approved`` 才能进入 release。
