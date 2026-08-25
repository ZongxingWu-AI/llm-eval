# 03 当裁判：法律回答评分

法律线不是把两个回答做 Pairwise 比较，而是把一个模型回答与参考答案、Rubric、法院依据和红线规则对照评分。
主要代码位于 ``methodology/03_当裁判/legal/scoring/legal_scorer.py``，由跑项目入口自动调用。
评分结果统一为 ``PASS``、``REVIEW``、``REJECT``，Calibration 阶段再与人工评分对照。
