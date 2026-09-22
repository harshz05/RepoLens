from typing import List, Optional
from packages.code_intel.models import ExtractedSymbol, ExtractedFileContext
from packages.code_intel.parsers.registry import parser_registry

def extract_file_symbols(code_content: str, file_path: str, language: str) -> List[ExtractedSymbol]:
    """
    Extract symbols using the Tree-sitter parser registry.
    Seamless drop-in upgrade from legacy AST/regex to Tree-sitter.
    """
    code_bytes = code_content.encode("utf-8")
    ctx = parser_registry.parse_file(code_bytes, file_path)
    if ctx:
        return ctx.symbols
    return []

__all__ = ["extract_file_symbols", "ExtractedSymbol"]
