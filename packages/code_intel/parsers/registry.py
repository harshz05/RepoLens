from pathlib import Path
from typing import Dict, Optional
from packages.code_intel.parsers.base import BaseLanguageParser
from packages.code_intel.parsers.python_parser import PythonTreeSitterParser
from packages.code_intel.parsers.typescript_parser import TypeScriptTreeSitterParser
from packages.code_intel.models import ExtractedFileContext

class ParserRegistry:
    """Central registry mapping file extensions and languages to Tree-sitter parsers."""

    def __init__(self):
        self._parsers: Dict[str, BaseLanguageParser] = {}
        self._py_parser = PythonTreeSitterParser()
        self._ts_parser = TypeScriptTreeSitterParser(mode="typescript")
        self._tsx_parser = TypeScriptTreeSitterParser(mode="tsx")
        self._js_parser = TypeScriptTreeSitterParser(mode="javascript")

        # Map extensions
        self._register(".py", self._py_parser)
        self._register(".ts", self._ts_parser)
        self._register(".mts", self._ts_parser)
        self._register(".cts", self._ts_parser)
        self._register(".tsx", self._tsx_parser)
        self._register(".js", self._js_parser)
        self._register(".jsx", self._tsx_parser)
        self._register(".mjs", self._js_parser)
        self._register(".cjs", self._js_parser)

    def _register(self, extension: str, parser: BaseLanguageParser) -> None:
        self._parsers[extension.lower()] = parser

    def get_parser_for_path(self, file_path: str) -> Optional[BaseLanguageParser]:
        """Look up parser by file extension."""
        ext = Path(file_path).suffix.lower()
        return self._parsers.get(ext)

    def parse_file(self, code_bytes: bytes, file_path: str) -> Optional[ExtractedFileContext]:
        """Parse file content using registered language parser."""
        parser = self.get_parser_for_path(file_path)
        if parser:
            return parser.parse(code_bytes, file_path)
        return None

# Global Singleton Instance
parser_registry = ParserRegistry()
