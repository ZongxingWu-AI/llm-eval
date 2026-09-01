"""法律题集和模型输入的个人信息扫描工具。"""
from __future__ import annotations
import importlib
import json
from typing import Any

_redactor = importlib.import_module("methodology.01_造Benchmark.legal.ingestion.pii_redaction")

def scan_pii(value: Any) -> list[str]:
    """扫描文本或结构化值中是否存在未脱敏个人信息。"""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return _redactor.contains_pii(text)
