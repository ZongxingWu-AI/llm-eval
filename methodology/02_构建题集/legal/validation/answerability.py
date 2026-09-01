"""法律题目的独立可作答性校验工具。"""
from __future__ import annotations
from typing import Any

def validate_answerability(question: dict[str, Any]) -> list[str]:
    """检查题目是否只依赖已保存的材料并且能够独立作答。"""
    issues=[]
    context=question.get("context")
    q=str(question.get("question") or "").strip()
    if not context or not str(context).strip(): issues.append("context 为空，题目不可独立作答")
    if not q: issues.append("question 为空")
    if str(context or "").strip()==q: issues.append("context 不能仅重复 question；必须提供独立案件材料")
    if any(x in q for x in ("根据上述","如上所述","上文","前述")): issues.append("question 依赖未保存的上文")
    fmt=question.get("question_format")
    if fmt in {"short_answer","case_analysis","legal_drafting"}:
        req=question.get("answer_requirements") or {}
        if req.get("must_include_reasoning") and not any(x in q for x in ("理由","依据","法律依据","说明")): issues.append("开放题要求理由但题面未明确说明")
    return issues
