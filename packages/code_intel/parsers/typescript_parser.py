import re
from typing import List, Optional, Tuple, Dict, Any
from tree_sitter import Language, Parser, Node
import tree_sitter_typescript as tstypescript
import tree_sitter_javascript as tsjavascript

from packages.code_intel.parsers.base import BaseLanguageParser
from packages.code_intel.models import (
    ExtractedSymbol,
    RawCallReference,
    RawImportReference,
    ExtractedFileContext,
)

TS_LANGUAGE = Language(tstypescript.language_typescript())
TSX_LANGUAGE = Language(tstypescript.language_tsx())
JS_LANGUAGE = Language(tsjavascript.language())

class TypeScriptTreeSitterParser(BaseLanguageParser):
    """Tree-sitter AST parser for TypeScript, TSX, JavaScript, and JSX source files."""

    def __init__(self, mode: str = "typescript"):
        self.mode = mode
        if mode == "tsx":
            self.parser = Parser(TSX_LANGUAGE)
        elif mode == "javascript":
            self.parser = Parser(JS_LANGUAGE)
        else:
            self.parser = Parser(TS_LANGUAGE)

    @property
    def language_name(self) -> str:
        return "typescript" if "typescript" in self.mode or self.mode == "tsx" else "javascript"

    def _has_jsx(self, node: Node) -> bool:
        """Check if AST subtree contains JSX elements."""
        if node.type in ("jsx_element", "jsx_fragment", "jsx_self_closing_element"):
            return True
        for child in node.children:
            if self._has_jsx(child):
                return True
        return False

    def _extract_docstring(self, node: Node, code_bytes: bytes) -> Optional[str]:
        """Extract JSDoc / multi-line comment preceding a node."""
        prev = node.prev_sibling
        if prev and prev.type == "comment":
            raw = self.node_text(prev, code_bytes)
            if raw.startswith("/**"):
                # Clean up JSDoc formatting
                lines = raw[3:-2].splitlines()
                cleaned = [re.sub(r"^\s*\*\s?", "", l) for l in lines]
                return "\n".join(cleaned).strip()
            return raw.strip()
        return None

    def parse(self, code_bytes: bytes, file_path: str) -> ExtractedFileContext:
        tree = self.parser.parse(code_bytes)
        root = tree.root_node

        symbols: List[ExtractedSymbol] = []
        calls: List[RawCallReference] = []
        imports: List[RawImportReference] = []
        framework_meta: Dict[str, Any] = {"components": [], "hooks": [], "interfaces": []}

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

            # 1. Interface & Type Alias Declarations
            if node.type in ("interface_declaration", "type_alias_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    iface_name = self.node_text(name_node, code_bytes)
                    fqn = get_fqn(iface_name)
                    s_line, s_col, e_line, e_col = self.get_line_col(node)
                    docstring = self._extract_docstring(node, code_bytes)

                    signature = f"interface {iface_name}" if node.type == "interface_declaration" else f"type {iface_name}"

                    symbols.append(
                        ExtractedSymbol(
                            name=iface_name,
                            fully_qualified_name=fqn,
                            kind="interface",
                            start_line=s_line,
                            end_line=e_line,
                            start_col=s_col,
                            end_col=e_col,
                            signature=signature,
                            docstring=docstring,
                            file_path=file_path,
                            parent_fqn=get_current_caller_fqn(),
                        )
                    )
                    framework_meta["interfaces"].append(iface_name)
                    return

            # 2. Class Declarations
            elif node.type == "class_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    class_name = self.node_text(name_node, code_bytes)
                    fqn = get_fqn(class_name)
                    s_line, s_col, e_line, e_col = self.get_line_col(node)
                    docstring = self._extract_docstring(node, code_bytes)

                    # Extract extends clause
                    superclasses = []
                    for child in node.children:
                        if child.type in ("class_heritage", "extends_clause"):
                            # Search for identifiers in heritage / extends
                            def find_bases(n: Node):
                                for sub in n.children:
                                    if sub.type in ("identifier", "type_identifier") and sub.type != "extends":
                                        base_name = self.node_text(sub, code_bytes)
                                        if base_name and base_name not in ("extends", "implements"):
                                            superclasses.append(base_name)
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
                                    elif sub.type in ("extends_clause", "heritage_clause"):
                                        find_bases(sub)
                            find_bases(child)

                    sig_bases = f" extends {', '.join(superclasses)}" if superclasses else ""
                    signature = f"class {class_name}{sig_bases}"

                    symbols.append(
                        ExtractedSymbol(
                            name=class_name,
                            fully_qualified_name=fqn,
                            kind="class",
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

                    body_node = node.child_by_field_name("body")
                    if body_node:
                        for child in body_node.children:
                            traverse(child)

                    scope_stack.pop()
                    current_class = old_class
                    return

            # 3. Method Definitions inside Classes
            elif node.type == "method_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    method_name = self.node_text(name_node, code_bytes)
                    fqn = get_fqn(method_name)
                    s_line, s_col, e_line, e_col = self.get_line_col(node)
                    docstring = self._extract_docstring(node, code_bytes)

                    params_node = node.child_by_field_name("parameters")
                    params_text = self.node_text(params_node, code_bytes) if params_node else "()"
                    return_node = node.child_by_field_name("return_type")
                    return_text = f": {self.node_text(return_node, code_bytes)}" if return_node else ""

                    is_async = any(c.type == "async" for c in node.children)
                    prefix = "async " if is_async else ""
                    signature = f"{prefix}{method_name}{params_text}{return_text}"

                    symbols.append(
                        ExtractedSymbol(
                            name=method_name,
                            fully_qualified_name=fqn,
                            kind="method",
                            start_line=s_line,
                            end_line=e_line,
                            start_col=s_col,
                            end_col=e_col,
                            signature=signature,
                            docstring=docstring,
                            file_path=file_path,
                            parent_fqn=get_current_caller_fqn(),
                            metadata={"is_async": is_async},
                        )
                    )

                    scope_stack.append(method_name)
                    body_node = node.child_by_field_name("body")
                    if body_node:
                        for child in body_node.children:
                            traverse(child)
                    scope_stack.pop()
                    return

            # 4. Function Declarations
            elif node.type in ("function_declaration", "generator_function_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    func_name = self.node_text(name_node, code_bytes)
                    fqn = get_fqn(func_name)
                    s_line, s_col, e_line, e_col = self.get_line_col(node)
                    docstring = self._extract_docstring(node, code_bytes)

                    params_node = node.child_by_field_name("parameters")
                    params_text = self.node_text(params_node, code_bytes) if params_node else "()"
                    return_node = node.child_by_field_name("return_type")
                    return_text = f": {self.node_text(return_node, code_bytes)}" if return_node else ""

                    is_async = any(c.type == "async" for c in node.children)
                    prefix = "async function" if is_async else "function"
                    signature = f"{prefix} {func_name}{params_text}{return_text}"

                    # Detect React Component or Custom Hook
                    kind = "function"
                    body_node = node.child_by_field_name("body")
                    if func_name.startswith("use") and len(func_name) > 3 and func_name[3].isupper():
                        kind = "hook"
                        framework_meta["hooks"].append(func_name)
                    elif func_name[0].isupper() and body_node and self._has_jsx(body_node):
                        kind = "component"
                        framework_meta["components"].append(func_name)

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
                            metadata={"is_async": is_async},
                        )
                    )

                    scope_stack.append(func_name)
                    if body_node:
                        for child in body_node.children:
                            traverse(child)
                    scope_stack.pop()
                    return

            # 5. Variable Declarations with Arrow Functions (`const foo = () => ...`)
            elif node.type in ("lexical_declaration", "variable_declaration"):
                for declarator in node.children:
                    if declarator.type == "variable_declarator":
                        name_node = declarator.child_by_field_name("name")
                        value_node = declarator.child_by_field_name("value")

                        if name_node and value_node and value_node.type in ("arrow_function", "function_expression"):
                            func_name = self.node_text(name_node, code_bytes)
                            fqn = get_fqn(func_name)
                            s_line, s_col, e_line, e_col = self.get_line_col(node)
                            docstring = self._extract_docstring(node, code_bytes)

                            params_node = value_node.child_by_field_name("parameters")
                            params_text = self.node_text(params_node, code_bytes) if params_node else "()"
                            return_node = value_node.child_by_field_name("return_type")
                            return_text = f": {self.node_text(return_node, code_bytes)}" if return_node else ""

                            is_async = any(c.type == "async" for c in value_node.children)
                            async_p = "async " if is_async else ""
                            signature = f"const {func_name} = {async_p}{params_text}{return_text} => ..."

                            kind = "function"
                            body_node = value_node.child_by_field_name("body")
                            if func_name.startswith("use") and len(func_name) > 3 and func_name[3].isupper():
                                kind = "hook"
                                framework_meta["hooks"].append(func_name)
                            elif func_name[0].isupper() and body_node and self._has_jsx(body_node):
                                kind = "component"
                                framework_meta["components"].append(func_name)

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
                                    metadata={"is_async": is_async},
                                )
                            )

                            scope_stack.append(func_name)
                            if body_node:
                                for child in body_node.children:
                                    traverse(child)
                            scope_stack.pop()
                            return

            # 6. Call Expressions (`foo()`, `obj.method()`)
            elif node.type == "call_expression":
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
                        # Check for CommonJS require('mod')
                        if callee_name == "require" and arg_strings:
                            req_mod = arg_strings[0].strip("'\"")
                            imports.append(
                                RawImportReference(
                                    module_name=req_mod,
                                    imported_symbol=None,
                                    alias=None,
                                    is_relative=req_mod.startswith("."),
                                    file_path=file_path,
                                    line_number=s_line,
                                )
                            )
                        elif callee_name not in ("console", "parseInt", "parseFloat", "String", "Number", "Boolean", "Object", "Array"):
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
                    elif func_child.type == "member_expression":
                        obj_node = func_child.child_by_field_name("object")
                        prop_node = func_child.child_by_field_name("property")
                        if prop_node:
                            method_name = self.node_text(prop_node, code_bytes)
                            obj_name = self.node_text(obj_node, code_bytes) if obj_node else None
                            calls.append(
                                RawCallReference(
                                    caller_fqn=caller_fqn,
                                    callee_name=method_name,
                                    callee_module=obj_name,
                                    line_number=s_line,
                                    col_offset=s_col,
                                    call_type="method_call",
                                    file_path=file_path,
                                    arguments=arg_strings,
                                )
                            )

            # 7. New Expressions (`new User()`)
            elif node.type == "new_expression":
                constructor_node = node.child_by_field_name("constructor")
                if constructor_node:
                    s_line, s_col, _, _ = self.get_line_col(node)
                    callee_name = self.node_text(constructor_node, code_bytes)
                    calls.append(
                        RawCallReference(
                            caller_fqn=get_current_caller_fqn(),
                            callee_name=callee_name,
                            callee_module=None,
                            line_number=s_line,
                            col_offset=s_col,
                            call_type="instantiates",
                            file_path=file_path,
                        )
                    )

            # 8. Import Statements (`import { a, b as c } from './mod'`)
            elif node.type == "import_statement":
                s_line, _, _, _ = self.get_line_col(node)
                source_node = node.child_by_field_name("source")
                if source_node:
                    mod_path = self.node_text(source_node, code_bytes).strip("'\"")
                    is_rel = mod_path.startswith(".")

                    # Named imports or default imports
                    import_clause = node.child_by_field_name("clause") or node
                    named_imports_node = None
                    for child in import_clause.children:
                        if child.type == "named_imports":
                            named_imports_node = child
                            break
                        elif child.type == "identifier":  # Default import
                            def_name = self.node_text(child, code_bytes)
                            imports.append(
                                RawImportReference(
                                    module_name=mod_path,
                                    imported_symbol=def_name,
                                    alias=None,
                                    is_relative=is_rel,
                                    file_path=file_path,
                                    line_number=s_line,
                                )
                            )

                    if named_imports_node:
                        for spec in named_imports_node.children:
                            if spec.type == "import_specifier":
                                name_c = spec.child_by_field_name("name")
                                alias_c = spec.child_by_field_name("alias")
                                if name_c:
                                    imports.append(
                                        RawImportReference(
                                            module_name=mod_path,
                                            imported_symbol=self.node_text(name_c, code_bytes),
                                            alias=self.node_text(alias_c, code_bytes) if alias_c else None,
                                            is_relative=is_rel,
                                            file_path=file_path,
                                            line_number=s_line,
                                        )
                                    )

                    # Namespace import (`import * as Foo from './mod'`)
                    for child in import_clause.children:
                        if child.type == "namespace_import":
                            ns_ident = None
                            for sub in child.children:
                                if sub.type == "identifier":
                                    ns_ident = self.node_text(sub, code_bytes)
                            imports.append(
                                RawImportReference(
                                    module_name=mod_path,
                                    imported_symbol="*",
                                    alias=ns_ident,
                                    is_relative=is_rel,
                                    file_path=file_path,
                                    line_number=s_line,
                                )
                            )

            # Recurse children
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
