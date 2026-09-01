"""法律案件外发文本的严格 PII 脱敏工具。

full_text 只能本地保存；本模块产生的 external_text 才允许进入模型 Prompt。
"""
from __future__ import annotations
import re
from typing import Iterable, Mapping

_CN_NUMBERS = "一二三四五六七八九十"

def _ordinal(kind: str, number: int) -> str:
    """返回适合外部文本阅读的中文序号占位符。"""
    suffix = _CN_NUMBERS[number - 1] if 0 < number <= len(_CN_NUMBERS) else str(number)
    return f"{kind}{suffix}"

PII_PATTERNS = {
    "身份证号": re.compile(r"(?<![0-9Xx])\d{17}[0-9Xx](?![0-9])"),
    "手机号": re.compile(r"(?<!\d)(?:1[3-9]\d{9})(?!\d)"),
    "固定电话": re.compile(r"(?<!\d)0\d{2,3}[-－ ]?\d{7,8}(?!\d)"),
    "邮箱": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "银行卡号": re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
    "统一社会信用代码": re.compile(r"(?<![0-9A-Z])[0-9A-Z]{18}(?![0-9A-Z])"),
    "车牌号": re.compile(r"(?<![\u4e00-\u9fffA-Z0-9])[\u4e00-\u9fff][A-Z][A-Z0-9]{5,6}(?![A-Z0-9])"),
    "出生日期": re.compile(r"\d{4}年\d{1,2}月\d{1,2}日出生"),
}

def _placeholder(kind: str, counters: dict[str, int]) -> str:
    """为一种敏感信息生成本案内稳定递增的占位符。"""
    counters[kind] = counters.get(kind, 0) + 1
    return _ordinal(kind, counters[kind])

def redact_pii(text: str, parties: Iterable[Mapping[str,str]] | None = None) -> tuple[str, dict[str,str]]:
    """返回严格脱敏文本和本案内部映射；映射不写入外部产物。"""
    result = str(text or "")
    mapping: dict[str,str] = {}
    counters: dict[str,int] = {}
    # 先替换主体，长名称优先，保证同案一致。
    party_items = [p for p in (parties or []) if isinstance(p, Mapping) and str(p.get("name") or "").strip()]
    role_counts: dict[str,int] = {}
    for party in sorted(party_items, key=lambda p: len(str(p.get("name") or "")), reverse=True):
        name = str(party.get("name") or "").strip()
        if len(name) < 2 or name in mapping:
            continue
        role = str(party.get("role") or "当事人")
        role_counts[role] = role_counts.get(role, 0) + 1
        # 外部文本使用稳定、非身份化角色编号。
        label = {"原告":"原告", "被告":"被告", "第三人":"第三人"}.get(role, "当事人") + str(role_counts[role])
        mapping[name] = label
        result = result.replace(name, label)
    # 常见敏感信息按首次出现顺序稳定编号。
    for kind, pattern in PII_PATTERNS.items():
        def repl(match, k=kind):
            """把单个敏感信息替换为本案内稳定占位符。"""
            value = match.group(0)
            if value in mapping:
                return mapping[value]
            label = _placeholder(k, counters)
            mapping[value] = label
            return label
        result = pattern.sub(repl, result)
    # 带字段名的地址和内部编号按完整原值建立映射：同值复用占位符，不同值递增。
    labelled_patterns = (
        ("地址", re.compile(r"(?P<prefix>住址|住所|地址|居住地)(?P<sep>\s*[:：]?\s*)(?P<value>[^，。；;\n]{4,80})")),
        ("病历号", re.compile(r"(?P<prefix>病历号)(?P<sep>\s*[:：]?\s*)(?P<value>[A-Za-z0-9-]{3,40})")),
        ("社保号", re.compile(r"(?P<prefix>社保号)(?P<sep>\s*[:：]?\s*)(?P<value>[A-Za-z0-9-]{3,40})")),
        ("内部编号", re.compile(r"(?P<prefix>内部编号|员工编号)(?P<sep>\s*[:：]?\s*)(?P<value>[A-Za-z0-9-]{3,40})")),
    )
    for kind, pattern in labelled_patterns:
        def replace_labelled(match, k=kind):
            """按字段替换敏感值，并在同一案件中复用稳定占位符。"""
            value = match.group("value").strip()
            key = f"{k}:{value}"
            label = mapping.get(key)
            if not label:
                counters[k] = counters.get(k, 0) + 1
                label = _ordinal(k, counters[k])
                mapping[key] = label
            return f"{match.group('prefix')}{match.group('sep')}{label}"
        result = pattern.sub(replace_labelled, result)
    return result, mapping

def contains_pii(text: str) -> list[str]:
    """返回仍命中的 PII 类型；严格模式下非空即失败。"""
    found=[]
    value=str(text or "")
    # 已生成的占位符不是新的地址/编号；先移除字段名后的占位符再做残留扫描。
    value = re.sub(r"(?:住址|住所|地址|居住地)\s*[:：]?\s*地址[一二三四五六七八九十0-9]", "", value)
    value = re.sub(r"(?:病历号|社保号|内部编号|员工编号)\s*[:：]?\s*(?:病历号|社保号|内部编号|员工编号)[一二三四五六七八九十0-9]", "", value)
    for kind, pattern in PII_PATTERNS.items():
        if pattern.search(value): found.append(kind)
    if re.search(r"(?:住址|住所|地址|居住地)\s*[:：]?\s*(?!地址[一二三四五六七八九十0-9])[^，。；;\n]{4,80}", value): found.append("地址")
    if re.search(r"(?:病历号|社保号|内部编号|员工编号)\s*[:：]?\s*(?![病历号社保号内部编号员工编号])[A-Za-z0-9-]{3,40}", value): found.append("内部编号")
    return sorted(set(found))

__all__=["PII_PATTERNS","redact_pii","contains_pii"]
