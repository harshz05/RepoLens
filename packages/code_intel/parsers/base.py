from abc import ABC, abstractmethod
from typing import Tuple, Optional
from tree_sitter import Node
from packages.code_intel.models import ExtractedFileContext

class BaseLanguageParser(ABC):
    """Abstract base class for all language-specific Tree-sitter parsers."""

    @property
    @abstractmethod
    def language_name(self) -> str:
        """Name of the programming language (e.g. 'python', 'typescript')."""
        pass

    @abstractmethod
    def parse(self, code_bytes: bytes, file_path: str) -> ExtractedFileContext:
        """
        Parse raw code bytes into an ExtractedFileContext containing
        normalized symbols, call expressions, and import statements.
        """
        pass

    @staticmethod
    def node_text(node: Optional[Node], code_bytes: bytes) -> str:
        """Safely extract UTF-8 text from a Tree-sitter AST node."""
        if node is None:
            return ""
        return code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore").strip()

    @staticmethod
    def get_line_col(node: Node) -> Tuple[int, int, int, int]:
        """
        Extract line and column boundaries from a node.
        Returns (start_line, start_col, end_line, end_col) with 1-indexed lines.
        """
        start_line = node.start_point[0] + 1
        start_col = node.start_point[1]
        end_line = node.end_point[0] + 1
        end_col = node.end_point[1]
        return start_line, start_col, end_line, end_col
