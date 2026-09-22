from typing import List, Dict, Optional, Tuple
from tree_sitter import Node
from packages.code_intel.parsers.registry import parser_registry

class CyclomaticComplexityCalculator:
    """
    Calculates McCabe Cyclomatic Complexity V(G) for function and method AST nodes.
    V(G) = 1 + D, where D is the count of branching decision points.
    """

    PYTHON_DECISION_NODES = {
        "if_statement",
        "elif_clause",
        "for_statement",
        "while_statement",
        "except_clause",
        "with_statement",
        "conditional_expression",
    }

    TS_JS_DECISION_NODES = {
        "if_statement",
        "for_statement",
        "for_in_statement",
        "while_statement",
        "do_statement",
        "catch_clause",
        "switch_case",
        "ternary_expression",
    }

    @classmethod
    def calculate_for_node(cls, root_node: Node, language: str) -> int:
        """Traverse subtree and count branching decision nodes."""
        complexity = 1
        lang_lower = language.lower()

        stack = [root_node]
        while stack:
            curr = stack.pop()

            if "python" in lang_lower:
                if curr.type in cls.PYTHON_DECISION_NODES:
                    complexity += 1
                elif curr.type == "boolean_operator":
                    complexity += 1

            elif "typescript" in lang_lower or "javascript" in lang_lower or "tsx" in lang_lower:
                if curr.type in cls.TS_JS_DECISION_NODES:
                    complexity += 1
                elif curr.type == "binary_expression":
                    # Check if operator child is &&, ||, ??
                    for child in curr.children:
                        if child.type in ("&&", "||", "??"):
                            complexity += 1
                            break

            for child in curr.children:
                stack.append(child)

        return complexity

    @classmethod
    def calculate_for_symbols(
        cls,
        code_bytes: bytes,
        file_path: str,
        language: str,
    ) -> List[Tuple[str, int, int, int]]:
        """
        Parses file CST and computes complexity for all functions/methods.
        Returns List of (symbol_name, start_line, end_line, complexity).
        """
        parser_inst = parser_registry.get_parser_for_path(file_path)
        if not parser_inst:
            return []

        # Access inner tree-sitter parser
        ts_parser = getattr(parser_inst, "parser", None)
        if not ts_parser:
            return []

        tree = ts_parser.parse(code_bytes)
        results: List[Tuple[str, int, int, int]] = []

        func_types = {
            "function_definition",
            "function_declaration",
            "method_definition",
            "arrow_function",
        }

        stack = [tree.root_node]
        while stack:
            curr = stack.pop()
            if curr.type in func_types:
                # Find name
                name = "anonymous"
                for child in curr.children:
                    if child.type in ("identifier", "property_identifier"):
                        name = code_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="ignore")
                        break

                start_line = curr.start_point[0] + 1
                end_line = curr.end_point[0] + 1
                cc = cls.calculate_for_node(curr, language)
                results.append((name, start_line, end_line, cc))

            for child in curr.children:
                stack.append(child)

        return results
