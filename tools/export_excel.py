"""项目模块：tools/export_excel.py。

本文件属于三条评测线或公共工具层的一部分，负责完成本文件名对应的处理步骤。输入来自上游函数或数据目录，输出返回给下游函数或写入对应结果目录。

项目位置：tools/export_excel.py。
主要用途：项目工具层，提供跨评测线的导出和辅助能力。
输入：输入来自各评测线的 JSON/JSONL 结果文件。
输出：输出写为用户指定的 Excel 或其他辅助文件。
上下游关系：本文件承接上游输入，并把返回值或生成文件交给同一评测线的下游步骤。
副作用：可能创建输出目录并写文件，不负责调用真实模型。
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable



def _flatten(value):
    """为同一文件中的公开流程提供一个小而明确的辅助步骤。

参数：value。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def export_jsonl(input_path: str | Path, output_path: str | Path | None = None,
                 max_items: int | None = None) -> Path:
    """读取 JSONL 并导出为 Excel 工作簿。

    输入：input_path 指向一行一个 JSON 对象的文件，output_path 可指定 xlsx 路径，
    max_items 用于试跑时限制读取行数。
    输出：返回实际生成的 Excel 路径。
    运行前数据形态：每个非空行是一个 JSON 对象，字段集合可以不完全一致。
    运行后数据变化：所有出现过的字段成为列，嵌套对象或数组通过 _flatten 变成单元格字符串。
    副作用：创建父目录并覆盖同名 xlsx 文件；需要 openpyxl，但不调用模型。
    异常或失败处理：输入文件不存在、JSON 行非法或缺少依赖时抛出异常。
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError as exc:
        raise RuntimeError("缺少 openpyxl 依赖") from exc
    source = Path(input_path)
    rows = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
        if max_items is not None and max_items > 0 and len(rows) >= max_items:
            break
    target = Path(output_path) if output_path else source.with_suffix(".xlsx")
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = source.stem[:31]
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    if columns:
        sheet.append(columns)
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E78")
        for row in rows:
            cells = []
            for column in columns:
                value = row.get(column, "")
                cells.append(_flatten(value))
            sheet.append(cells)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column_cells in sheet.columns:
            max_length = min(60, max(len(str(cell.value or "")) for cell in column_cells) + 2)
            sheet.column_dimensions[column_cells[0].column_letter].width = max(10, max_length)
            for cell in column_cells[1:]:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
    workbook.save(target)
    return target


def discover_jsonl() -> Iterable[Path]:
    """扫描指定目录下可以导出的 JSONL 文件。调用后返回排序后的文件路径列表，不读取或修改文件内容。"""

    for track in ("ceval", "pairwise_judge", "legal_benchmark"):
        root = PROJECT_ROOT / "tracks" / track
        for folder_name in ("data", "results"):
            folder = root / folder_name
            if folder.exists():
                yield from sorted(folder.rglob("*.jsonl"))


def main() -> None:
    """完成当前模块中的一个处理步骤。

参数：无。
返回：根据函数实现返回处理结果，或在输入不合法时抛出异常。
数据变化：调用前接收上游的原始值或结构化对象，调用后返回更适合下游使用的值；如果函数写文件或改变环境，会在实现中明确说明。"""

    parser = argparse.ArgumentParser(description="把评测 JSONL 导出为 Excel")
    parser.add_argument("--input", help="单个 JSONL；不传则扫描三条评测线")
    parser.add_argument("--output", help="单文件输出 XLSX；批量模式不可用")
    parser.add_argument("--max-items", type=int, default=None, help="每个文件最多导出前 N 行")
    args = parser.parse_args()
    if args.input:
        target = export_jsonl(args.input, args.output, args.max_items)
        print(f"完成：{target}")
        return
    if args.output:
        parser.error("--output 只能与 --input 一起使用")
    count = 0
    for source in discover_jsonl():
        target = export_jsonl(source, max_items=args.max_items)
        print(f"{source} -> {target}")
        count += 1
    print(f"共导出 {count} 个文件")


if __name__ == "__main__":
    main()
