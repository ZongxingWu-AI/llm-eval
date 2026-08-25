import ast
from pathlib import Path
root=Path(r'C:\CEval-LLMJudge')
for p in root.glob('**/*.py'):
    if any(x in p.parts for x in ['.git','__pycache__']): continue
    tree=ast.parse(p.read_text(encoding='utf-8'))
    missing=[]
    if not ast.get_docstring(tree): missing.append('MODULE')
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and not ast.get_docstring(n): missing.append(f'{n.name}@{n.lineno}')
    if missing: print(p.relative_to(root), missing)
