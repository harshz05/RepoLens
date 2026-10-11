import re
from typing import List, Optional, Tuple, Dict, Any
from tree_sitter import Language, Parser, Node
import tree_sitter_python as tspython

from packages.code_intel.parsers.base import BaseLanguageParser
from packages.code_intel.parsers.route_utils import extract_route_info
from packages.code_intel.models import (
    ExtractedSymbol,
    RawCallReference,
    RawImportReference,
    ExtractedFileContext,
)

PY_LANGUAGE = Language(tspython.language())

class PythonTreeSitterParser(BaseLanguageParser):
    """Tree-sitter AST parser for Python source files."""

    def __init__(self):
        self.parser = Parser(PY_LANGUAGE)

    @property
    def language_name(self) -> str:
        return "python"

    def _extract_docstring(self, body_node: Optional[Node], code_bytes: bytes) -> Optional[str]:
        """Extract docstring from the first statement in a function/class body block."""
        if not body_node:
            return None

        for child in body_node.children:
            if child.type == "expression_statement":
                for expr in child.children:
                    if expr.type == "string":
                        raw = self.node_text(expr, code_bytes)
                        # Strip outer quotes (''' or \"\"\" or ' or \")
                        if raw.startswith(('"""', "'''")):
                            return raw[3:-3].strip()
                        elif raw.startswith(('"', "'")):
                            return raw[1:-1].strip()
                        return raw.strip()
                break
            elif child.type not in ("comment", "\n"):
                break
        return None

    def _extract_decorators(self, node: Node, code_bytes: bytes) -> List[str]:
        """Extract decorator strings if parent or node is a decorated_definition."""
        decorators = []
        target = node
        if node.parent and node.parent.type == "decorated_definition":
            target = node.parent

        if target.type == "decorated_definition":
            for child in target.children:
                if child.type == "decorator":
                    dec_text = self.node_text(child, code_bytes)
                    decorators.append(dec_text)
        return decorators

    def parse(self, code_bytes: bytes, file_path: str) -> ExtractedFileContext:
        tree = self.parser.parse(code_bytes)
        root = tree.root_node

        symbols: List[ExtractedSymbol] = []
        calls: List[RawCallReference] = []
        imports: List[RawImportReference] = []
        framework_meta: Dict[str, Any] = {"routes": [], "db_models": []}

        scope_stack: List[str] = []
        current_class: Optional[str] = None

        def get_fqn(name: str) -> str:
            if scope_stack:
                return f"{file_path}::{'.'.join(scope_stack)}.{name}"
            return f"{file_path}::{name}"

        def get_current_caller_fqn() -> Optional[str]:
            if scope_stack:
                return f"{file_path}::{'.'.join(scope_stack)}"
            return None

        def traverse(node: Node):
            nonlocal current_class

            # 1. Class Definitions
            if node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    class_name = self.node_text(name_node, code_bytes)
                    fqn = get_fqn(class_name)
                    s_line, s_col, e_line, e_col = self.get_line_col(node)
                    body_node = node.child_by_field_name("body")
                    docstring = self._extract_docstring(body_node, code_bytes)

                    # Extract base classes / superclasses
                    superclasses = []
                    superclasses_node = node.child_by_field_name("superclasses")
                    if superclasses_node:
                        for arg in superclasses_node.children:
                            if arg.type in ("identifier", "attribute"):
                                base_name = self.node_text(arg, code_bytes)
                                superclasses.append(base_name)
                                # Record inheritance dependency
                                calls.append(
                                    RawCallReference(
                                        caller_fqn=fqn,
                                        callee_name=base_name,
                                        callee_module=None,
                                        line_number=s_line,
                                        col_offset=s_col,
                                        call_type="inheritance",
                                        file_path=file_path,
                                    )
                                )

                    kind = "class"
                    if any("Base" in b or "Model" in b or "Declarative" in b for b in superclasses):
                        kind = "db_model"
                        framework_meta["db_models"].append({"name": class_name, "fqn": fqn, "bases": superclasses})

                    sig_bases = f"({', '.join(superclasses)})" if superclasses else ""
                    signature = f"class {class_name}{sig_bases}"

                    symbols.append(
                        ExtractedSymbol(
                            name=class_name,
                            fully_qualified_name=fqn,
                            kind=kind,
                            start_line=s_line,
                            end_line=e_line,
                            start_col=s_col,
                            end_col=e_col,
                            signature=signature,
                            docstring=docstring,
                            file_path=file_path,
                            parent_fqn=get_current_caller_fqn(),
                            metadata={"superclasses": superclasses},
                        )
                    )

                    old_class = current_class
                    current_class = class_name
                    scope_stack.append(class_name)

                    if body_node:
                        for child in body_node.children:
                            traverse(child)

                    scope_stack.pop()
                    current_class = old_class
                    return

            # 2. Function & Method Definitions
            elif node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    func_name = self.node_text(name_node, code_bytes)
                    fqn = get_fqn(func_name)
                    s_line, s_col, e_line, e_col = self.get_line_col(node)
                    body_node = node.child_by_field_name("body")
                    docstring = self._extract_docstring(body_node, code_bytes)

                    params_node = node.child_by_field_name("parameters")
                    params_text = self.node_text(params_node, code_bytes) if params_node else "()"
                    return_node = node.child_by_field_name("return_type")
                    return_text = f" -> {self.node_text(return_node, code_bytes)}" if return_node else ""

                    # Check if async
                    is_async = any(c.type == "async" for c in node.children)
                    prefix = "async def" if is_async else "def"
                    signature = f"{prefix} {func_name}{params_text}{return_text}"

                    # Determine symbol kind
                    decorators = self._extract_decorators(node, code_bytes)
                    kind = "method" if current_class else "function"

                    route_meta: Dict[str, Any] = {}
                    for dec in decorators:
                        dec_lower = dec.lower()
                        if any(m in dec_lower for m in [".get(", ".post(", ".put(", ".delete(", ".patch(", "@app.", "@router.", "@bp.route", ".route("]):
                            kind = "api_endpoint"
                            route_meta = extract_route_info(dec) or {}
                            framework_meta["routes"].append({
                                "name": func_name,
                                "fqn": fqn,
                                "decorator": dec,
                                "line": s_line,
                                **route_meta,
                            })
                            break

                    symbols.append(
                        ExtractedSymbol(
                            name=func_name,
                            fully_qualified_name=fqn,
                            kind=kind,
                            start_line=s_line,
                            end_line=e_line,
                            start_col=s_col,
                            end_col=e_col,
                            signature=signature,
                            docstring=docstring,
                            file_path=file_path,
                            parent_fqn=get_current_caller_fqn(),
                            metadata={"decorators": decorators, "is_async": is_async, **route_meta},
                        )
                    )

                    scope_stack.append(func_name)
                    if body_node:
                        for child in body_node.children:
                            traverse(child)
                    scope_stack.pop()
                    return

            # 3. Call Expressions
            elif node.type == "call":
                func_child = node.child_by_field_name("function")
                if func_child:
                    s_line, s_col, _, _ = self.get_line_col(node)
                    caller_fqn = get_current_caller_fqn()

                    args_node = node.child_by_field_name("arguments")
                    arg_strings = []
                    if args_node:
                        for arg in args_node.children:
                            if arg.type not in ("(", ")", ","):
                                arg_strings.append(self.node_text(arg, code_bytes))

                    if func_child.type == "identifier":
                        callee_name = self.node_text(func_child, code_bytes)
                        # Ignore common Python builtins to keep graph developer-focused
                        if callee_name not in ("print", "len", "range", "str", "int", "float", "bool", "dict", "list", "set", "tuple", "isinstance", "getattr", "hasattr", "setattr"):
                            call_type = "instantiates" if callee_name[0].isupper() else "call"
                            calls.append(
                                RawCallReference(
                                    caller_fqn=caller_fqn,
                                    callee_name=callee_name,
                                    callee_module=None,
                                    line_number=s_line,
                                    col_offset=s_col,
                                    call_type=call_type,
                                    file_path=file_path,
                                    arguments=arg_strings,
                                )
                            )
                    elif func_child.type == "attribute":
                        obj_node = func_child.child_by_field_name("object")
                        attr_node = func_child.child_by_field_name("attribute")
                        if attr_node:
                            attr_name = self.node_text(attr_node, code_bytes)
                            obj_name = self.node_text(obj_node, code_bytes) if obj_node else None

                            call_type = "method_call"
                            calls.append(
                                RawCallReference(
                                    caller_fqn=caller_fqn,
                                    callee_name=attr_name,
                                    callee_module=obj_name,
                                    line_number=s_line,
                                    col_offset=s_col,
                                    call_type=call_type,
                                    file_path=file_path,
                                    arguments=arg_strings,
                                )
                            )

            # 4. Import Statements (`import foo`, `import foo.bar as b`)
            elif node.type == "import_statement":
                s_line, _, _, _ = self.get_line_col(node)
                for child in node.children:
                    if child.type == "dotted_name":
                        mod = self.node_text(child, code_bytes)
                        imports.append(
                            RawImportReference(
                                module_name=mod,
                                imported_symbol=None,
                                alias=None,
                                is_relative=False,
                                file_path=file_path,
                                line_number=s_line,
                            )
                        )
                    elif child.type == "aliased_import":
                        name_c = child.child_by_field_name("name")
                        alias_c = child.child_by_field_name("alias")
                        if name_c:
                            imports.append(
                                RawImportReference(
                                    module_name=self.node_text(name_c, code_bytes),
                                    imported_symbol=None,
                                    alias=self.node_text(alias_c, code_bytes) if alias_c else None,
                                    is_relative=False,
                                    file_path=file_path,
                                    line_number=s_line,
                                    )
                            )

            # 5. From Import Statements (`from foo import bar, baz as b`, `from . import local`)
            elif node.type == "import_from_statement":
                s_line, _, _, _ = self.get_line_col(node)
                mod_name = ""
                is_rel = False

                mod_node = node.child_by_field_name("module_name")
                if mod_node:
                    mod_name = self.node_text(mod_node, code_bytes)

                # Check for relative dots
                for child in node.children:
                    if child.type == "relative_import":
                        is_rel = True
                        rel_text = self.node_text(child, code_bytes)
                        mod_name = rel_text + mod_name
                    elif child.type == "dotted_name" and not mod_node:
                        mod_name = self.node_text(child, code_bytes)

                # Extract imported names
                for child in node.children:
                    if child.type == "dotted_name" and child != mod_node:
                        sym_name = self.node_text(child, code_bytes)
                        imports.append(
                            RawImportReference(
                                module_name=mod_name,
                                imported_symbol=sym_name,
                                alias=None,
                                is_relative=is_rel,
                                file_path=file_path,
                                line_number=s_line,
                            )
                        )
                    elif child.type == "aliased_import":
                        name_c = child.child_by_field_name("name")
                        alias_c = child.child_by_field_name("alias")
                        if name_c:
                            imports.append(
                                RawImportReference(
                                    module_name=mod_name,
                                    imported_symbol=self.node_text(name_c, code_bytes),
                                    alias=self.node_text(alias_c, code_bytes) if alias_c else None,
                                    is_relative=is_rel,
                                    file_path=file_path,
                                    line_number=s_line,
                                )
                            )

            # Recurse through children
            for child in node.children:
                traverse(child)

        traverse(root)

        return ExtractedFileContext(
            file_path=file_path,
            language=self.language_name,
            symbols=symbols,
            calls=calls,
            imports=imports,
            framework_metadata=framework_meta,
        )