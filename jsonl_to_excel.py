"""JSONL 转 Excel 工具的根目录兼容入口。"""

from Jsonl2Excel.jsonl_to_excel import (
    convert_jsonl_to_excel,
    interactive_main,
)

__all__ = ["convert_jsonl_to_excel", "interactive_main"]


if __name__ == "__main__":
    interactive_main()
