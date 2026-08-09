import ast
import re
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ExtractedSymbol:
    name: str
    fully_qualified_name: str
    kind: str
    start_line: int
    end_line: int
    start_col: int
    end_col: int
    signature: Optional[str] = None
    docstring: Optional[str] = None

class PythonSymbolVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.symbols: List[ExtractedSymbol] = []
        self.scope_stack: List[str] = []

    def _get_fqn(self, name: str) -> str:
        if self.scope_stack:
            return f"{self.file_path}::{'.'.join(self.scope_stack)}.{name}"
        return f"{self.file_path}::{name}"

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        fqn = self._get_fqn(node.name)
        docstring = ast.get_docstring(node)
        
        kind = "class"
        for base in node.bases:
            base_str = ast.unparse(base) if hasattr(ast, "unparse") else ""
            if "Base" in base_str or "Model" in base_str:
                kind = "db_model"

        symbol = ExtractedSymbol(
            name=node.name,
            fully_qualified_name=fqn,
            kind=kind,
            start_line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            start_col=node.col_offset,
            end_col=getattr(node, "end_col_offset", node.col_offset),
            signature=f"class {node.name}",
            docstring=docstring,
        )
        self.symbols.append(symbol)

        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_func(node, is_async=True)

    def _handle_func(self, node, is_async: bool = False) -> None:
        fqn = self._get_fqn(node.name)
        docstring = ast.get_docstring(node)
        kind = "method" if self.scope_stack else "function"

        for decorator in node.decorator_list:
            dec_str = ast.unparse(decorator) if hasattr(ast, "unparse") else ""
            if any(method in dec_str for method in [".get", ".post", ".put", ".delete", ".patch", "@app.", "@router."]):
                kind = "api_endpoint"
                break

        sig_args = [arg.arg for arg in node.args.args]
        prefix = "async def" if is_async else "def"
        signature = f"{prefix} {node.name}({', '.join(sig_args)})"

        symbol = ExtractedSymbol(
            name=node.name,
            fully_qualified_name=fqn,
            kind=kind,
            start_line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            start_col=node.col_offset,
            end_col=getattr(node, "end_col_offset", node.col_offset),
            signature=signature,
            docstring=docstring,
        )
        self.symbols.append(symbol)

        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

def extract_python_symbols(code_content: str, file_path: str) -> List[ExtractedSymbol]:
    try:
        tree = ast.parse(code_content, filename=file_path)
        visitor = PythonSymbolVisitor(file_path=file_path)
        visitor.visit(tree)
        return visitor.symbols
    except Exception:
        return []

TS_FUNC_PATTERN = re.compile(
    r'^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)', re.MULTILINE
)
TS_CLASS_PATTERN = re.compile(
    r'^(?:export\s+)?class\s+([A-Za-z0-9_]+)(?:\s+extends\s+[A-Za-z0-9_]+)?', re.MULTILINE
)
TS_INTERFACE_PATTERN = re.compile(
    r'^(?:export\s+)?interface\s+([A-Za-z0-9_]+)', re.MULTILINE
)
TS_CONST_FUNC_PATTERN = re.compile(
    r'^(?:export\s+)?const\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>', re.MULTILINE
)

def extract_typescript_symbols(code_content: str, file_path: str) -> List[ExtractedSymbol]:
    symbols: List[ExtractedSymbol] = []
    lines = code_content.splitlines()

    for idx, line in enumerate(lines, start=1):
        line_str = line.strip()

        class_match = TS_CLASS_PATTERN.search(line_str)
        if class_match:
            name = class_match.group(1)
            symbols.append(ExtractedSymbol(
                name=name,
                fully_qualified_name=f"{file_path}::{name}",
                kind="class",
                start_line=idx,
                end_line=idx + 10,
                start_col=0,
                end_col=len(line),
                signature=f"class {name}"
            ))

        if not class_match:
            iface_match = TS_INTERFACE_PATTERN.search(line_str)
            if iface_match:
                name = iface_match.group(1)
                symbols.append(ExtractedSymbol(
                    name=name,
                    fully_qualified_name=f"{file_path}::{name}",
                    kind="interface",
                    start_line=idx,
                    end_line=idx + 5,
                    start_col=0,
                    end_col=len(line),
                    signature=f"interface {name}"
                ))

        func_match = TS_FUNC_PATTERN.search(line_str) or TS_CONST_FUNC_PATTERN.search(line_str)
        if func_match:
            name = func_match.group(1)
            args = func_match.group(2) if len(func_match.groups()) > 1 else ""
            symbols.append(ExtractedSymbol(
                name=name,
                fully_qualified_name=f"{file_path}::{name}",
                kind="function",
                start_line=idx,
                end_line=idx + 5,
                start_col=0,
                end_col=len(line),
                signature=f"function {name}({args})"
            ))

    return symbols

def extract_file_symbols(code_content: str, file_path: str, language: str) -> List[ExtractedSymbol]:
    if language == "python":
        return extract_python_symbols(code_content, file_path)
    elif language in ("typescript", "javascript"):
        return extract_typescript_symbols(code_content, file_path)
    return []
