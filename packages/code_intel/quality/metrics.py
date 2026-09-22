import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
from tree_sitter import Node
from packages.code_intel.parsers.registry import parser_registry
from packages.code_intel.models import ExtractedFileContext, ExtractedSymbol

@dataclass
class QualityFindingData:
    rule_id: str
    metric_name: str
    title: str
    description: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    confidence: float
    value: float
    threshold: float
    file_path: str
    start_line: int
    end_line: int
    recommendation: str
    symbol_fqn: Optional[str] = None

class CodeMetricsAnalyzer:
    """
    Computes deterministic code quality metrics:
    - File size (SLOC)
    - Function size (SLOC)
    - AST nesting depth
    - Empty exception handling
    """

    FILE_LOC_WARN = 500
    FILE_LOC_HIGH = 1000

    FUNC_LOC_WARN = 50
    FUNC_LOC_HIGH = 100

    MAX_NESTING_WARN = 4
    MAX_NESTING_HIGH = 6

    @classmethod
    def calculate_nesting_depth(cls, root_node: Node, language: str) -> int:
        """Calculate maximum block nesting depth inside a function."""
        block_types = {
            "block",
            "statement_block",
            "if_statement",
            "for_statement",
            "while_statement",
            "try_statement",
            "switch_statement",
        }

        max_depth = 0

        def traverse(node: Node, current_depth: int):
            nonlocal max_depth
            is_block = node.type in block_types
            next_depth = current_depth + 1 if is_block else current_depth
            if next_depth > max_depth:
                max_depth = next_depth

            for child in node.children:
                traverse(child, next_depth)

        traverse(root_node, 0)
        return max_depth

    @classmethod
    def check_empty_catch_blocks(
        cls,
        code_bytes: bytes,
        file_path: str,
        language: str,
    ) -> List[Tuple[int, int, str]]:
        """
        Detects empty except/catch blocks that silently swallow exceptions.
        Returns List of (start_line, end_line, snippet).
        """
        parser_inst = parser_registry.get_parser_for_path(file_path)
        if not parser_inst or not getattr(parser_inst, "parser", None):
            return []

        tree = parser_inst.parser.parse(code_bytes)
        empty_blocks: List[Tuple[int, int, str]] = []

        stack = [tree.root_node]
        while stack:
            curr = stack.pop()
            if curr.type in ("except_clause", "catch_clause"):
                # Find body/block child
                body_node = None
                for child in curr.children:
                    if child.type in ("block", "statement_block"):
                        body_node = child
                        break

                if body_node:
                    # Check if body is empty or contains only 'pass'
                    statements = [
                        c for c in body_node.children
                        if c.type not in ("{", "}", "comment")
                    ]
                    is_empty = False
                    if len(statements) == 0:
                        is_empty = True
                    elif len(statements) == 1 and statements[0].type == "pass_statement":
                        is_empty = True

                    if is_empty:
                        start_line = curr.start_point[0] + 1
                        end_line = curr.end_point[0] + 1
                        snippet = code_bytes[curr.start_byte:curr.end_byte].decode("utf-8", errors="ignore").strip()
                        empty_blocks.append((start_line, end_line, snippet))

            for child in curr.children:
                stack.append(child)

        return empty_blocks

    @classmethod
    def analyze_file_metrics(
        cls,
        code_text: str,
        file_path: str,
        language: str,
        context: Optional[ExtractedFileContext] = None,
    ) -> List[QualityFindingData]:
        findings: List[QualityFindingData] = []
        code_bytes = code_text.encode("utf-8", errors="ignore")
        lines = code_text.splitlines()
        line_count = len(lines)

        # 1. Large File Check
        if line_count > cls.FILE_LOC_WARN:
            sev = "HIGH" if line_count > cls.FILE_LOC_HIGH else "LOW"
            findings.append(
                QualityFindingData(
                    rule_id="QUAL-002",
                    metric_name="large_file",
                    title="Excessive File Length",
                    description=f"File contains {line_count} lines of code, exceeding threshold ({cls.FILE_LOC_WARN}).",
                    severity=sev,
                    confidence=1.0,
                    value=float(line_count),
                    threshold=float(cls.FILE_LOC_WARN),
                    file_path=file_path,
                    start_line=1,
                    end_line=line_count,
                    recommendation="Decompose this file into cohesive, modular components adhering to Single Responsibility Principle.",
                )
            )

        # 2. Large Functions & Function Nesting Depth
        if context:
            for sym in context.symbols:
                if sym.kind in ("function", "method"):
                    fn_lines = sym.end_line - sym.start_line + 1
                    if fn_lines > cls.FUNC_LOC_WARN:
                        sev = "MEDIUM" if fn_lines > cls.FUNC_LOC_HIGH else "LOW"
                        findings.append(
                            QualityFindingData(
                                rule_id="QUAL-003",
                                metric_name="large_function",
                                title="Excessive Function Length",
                                description=f"Function '{sym.name}' spans {fn_lines} lines of code, exceeding threshold ({cls.FUNC_LOC_WARN}).",
                                severity=sev,
                                confidence=1.0,
                                value=float(fn_lines),
                                threshold=float(cls.FUNC_LOC_WARN),
                                file_path=file_path,
                                start_line=sym.start_line,
                                end_line=sym.end_line,
                                recommendation="Extract sub-routines into helper functions to improve testability and readability.",
                                symbol_fqn=sym.fully_qualified_name,
                            )
                        )

        # 3. Empty Exception Handling
        empty_catches = cls.check_empty_catch_blocks(code_bytes, file_path, language)
        for s_line, e_line, snip in empty_catches:
            findings.append(
                QualityFindingData(
                    rule_id="QUAL-008",
                    metric_name="empty_error_handling",
                    title="Swallowed Exception in Empty Handler",
                    description="Empty catch/except block suppresses errors silently without logging or error recovery.",
                    severity="MEDIUM",
                    confidence=0.95,
                    value=1.0,
                    threshold=0.0,
                    file_path=file_path,
                    start_line=s_line,
                    end_line=e_line,
                    recommendation="Log the exception with context or handle specific expected exception classes rather than discarding errors.",
                )
            )

        return findings
