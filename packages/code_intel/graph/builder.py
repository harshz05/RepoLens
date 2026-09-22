from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set, Any
from packages.code_intel.models import (
    ExtractedSymbol,
    ExtractedFileContext,
    RawCallReference,
    RawImportReference,
    ResolvedDependency,
)

class DependencyGraphBuilder:
    """
    Constructs multi-file dependency call-graphs from extracted file contexts.
    Performs two-pass static resolution across intra-file and imported symbols.
    """

    def __init__(self, contexts: List[ExtractedFileContext]):
        self.contexts = contexts
        self.fqn_index: Dict[str, ExtractedSymbol] = {}
        self.name_index: Dict[str, List[ExtractedSymbol]] = {}
        self.file_symbols: Dict[str, List[ExtractedSymbol]] = {}
        self.file_imports: Dict[str, List[RawImportReference]] = {}
        self.class_methods: Dict[str, Dict[str, ExtractedSymbol]] = {}

        self._build_indexes()

    def _normalize_path(self, path_str: str) -> str:
        return Path(path_str).as_posix()

    def _build_indexes(self) -> None:
        """Index all extracted symbols and imports for O(1) resolution."""
        for ctx in self.contexts:
            norm_file = self._normalize_path(ctx.file_path)
            self.file_symbols[norm_file] = ctx.symbols
            self.file_imports[norm_file] = ctx.imports

            for sym in ctx.symbols:
                self.fqn_index[sym.fully_qualified_name] = sym

                if sym.name not in self.name_index:
                    self.name_index[sym.name] = []
                self.name_index[sym.name].append(sym)

                # Index class methods
                if sym.kind == "method" and sym.parent_fqn:
                    if sym.parent_fqn not in self.class_methods:
                        self.class_methods[sym.parent_fqn] = {}
                    self.class_methods[sym.parent_fqn][sym.name] = sym

    def _resolve_module_to_file(self, module_str: str, source_file: str) -> Optional[str]:
        """Convert an import module string (e.g. 'utils.crypto' or './helpers') to a project file path."""
        source_dir = Path(source_file).parent

        # 1. Handle relative imports ('./foo', '../bar', '.utils')
        if module_str.startswith("."):
            dots = len(module_str) - len(module_str.lstrip("."))
            clean_mod = module_str.lstrip(".").replace(".", "/")

            target_dir = source_dir
            for _ in range(dots - 1):
                target_dir = target_dir.parent

            candidate = (target_dir / clean_mod).as_posix() if clean_mod else target_dir.as_posix()
            for ext in (".py", ".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.js", "/__init__.py"):
                test_path = candidate + ext
                if test_path in self.file_symbols:
                    return test_path

        # 2. Handle absolute module paths ('packages.db.models', 'apps/api/app/schemas')
        mod_as_path = module_str.replace(".", "/")
        for file_p in self.file_symbols.keys():
            if file_p.startswith(mod_as_path) or mod_as_path in file_p:
                return file_p
            # Check without extension
            file_no_ext = str(Path(file_p).with_suffix("")).replace("\\", "/")
            if file_no_ext.endswith(mod_as_path):
                return file_p

        return None

    def resolve_dependencies(
        self,
        symbol_db_map: Optional[Dict[str, str]] = None,
        file_db_map: Optional[Dict[str, str]] = None,
    ) -> List[ResolvedDependency]:
        """
        Resolve all raw call references across files into verified ResolvedDependency objects.
        Optionally links to existing database primary key IDs.
        """
        resolved: List[ResolvedDependency] = []
        seen_edges: Set[Tuple[str, str, str, int]] = set()

        for ctx in self.contexts:
            source_file = self._normalize_path(ctx.file_path)
            file_id = file_db_map.get(source_file) if file_db_map else None
            imports = self.file_imports.get(source_file, [])
            local_symbols = self.file_symbols.get(source_file, [])
            local_symbol_names = {s.name: s for s in local_symbols}

            # Map imported names to target files/symbols
            import_symbol_map: Dict[str, Tuple[str, str]] = {}  # name_in_file -> (target_file, target_sym_name)
            for imp in imports:
                target_file = self._resolve_module_to_file(imp.module_name, source_file)
                if target_file:
                    name_key = imp.alias or imp.imported_symbol or imp.module_name
                    target_sym = imp.imported_symbol or name_key
                    import_symbol_map[name_key] = (target_file, target_sym)

            for call in ctx.calls:
                caller_fqn = call.caller_fqn
                callee_name = call.callee_name
                callee_module = call.callee_module
                line_no = call.line_number
                call_type = call.call_type

                target_sym: Optional[ExtractedSymbol] = None

                # Strategy 1: Intra-Class method call (self.foo(), this.foo())
                if callee_module in ("self", "this") and caller_fqn:
                    parent_class_fqn = caller_fqn.rsplit(".", 1)[0]
                    if parent_class_fqn in self.class_methods:
                        target_sym = self.class_methods[parent_class_fqn].get(callee_name)

                # Strategy 2: Intra-File function or class reference
                if not target_sym and callee_name in local_symbol_names:
                    candidate = local_symbol_names[callee_name]
                    # Avoid self-referencing loop unless recursive
                    if candidate.fully_qualified_name != caller_fqn:
                        target_sym = candidate

                # Strategy 3: Explicit Imported Symbol
                if not target_sym and callee_name in import_symbol_map:
                    tgt_file, tgt_name = import_symbol_map[callee_name]
                    tgt_fqn = f"{tgt_file}::{tgt_name}"
                    if tgt_fqn in self.fqn_index:
                        target_sym = self.fqn_index[tgt_fqn]
                    elif tgt_file in self.file_symbols:
                        # Find symbol in target file
                        for s in self.file_symbols[tgt_file]:
                            if s.name == tgt_name:
                                target_sym = s
                                break

                # Strategy 4: Imported Module Call (e.g. `utils.format_date()`)
                if not target_sym and callee_module and callee_module in import_symbol_map:
                    tgt_file, _ = import_symbol_map[callee_module]
                    tgt_fqn = f"{tgt_file}::{callee_name}"
                    if tgt_fqn in self.fqn_index:
                        target_sym = self.fqn_index[tgt_fqn]

                # Strategy 5: Class Inheritance
                if not target_sym and call_type == "inheritance":
                    if callee_name in local_symbol_names:
                        target_sym = local_symbol_names[callee_name]
                    elif callee_name in self.name_index and len(self.name_index[callee_name]) == 1:
                        target_sym = self.name_index[callee_name][0]

                # Strategy 6: Unique Unambiguous Global Match (Confidence 0.85)
                if not target_sym and callee_name in self.name_index:
                    candidates = self.name_index[callee_name]
                    # If exactly one symbol with this name exists project-wide
                    if len(candidates) == 1:
                        target_sym = candidates[0]

                # If target was resolved, emit dependency edge
                if target_sym and caller_fqn:
                    callee_fqn = target_sym.fully_qualified_name

                    # Deduplicate edge
                    edge_key = (caller_fqn, callee_fqn, call_type, line_no)
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)

                        caller_sym_id = symbol_db_map.get(caller_fqn) if symbol_db_map else None
                        callee_sym_id = symbol_db_map.get(callee_fqn) if symbol_db_map else None

                        resolved.append(
                            ResolvedDependency(
                                caller_symbol_id=caller_sym_id,
                                callee_symbol_id=callee_sym_id,
                                caller_fqn=caller_fqn,
                                callee_fqn=callee_fqn,
                                dependency_type=call_type,
                                file_id=file_id,
                                file_path=source_file,
                                line_number=line_no,
                                confidence=1.0,
                            )
                        )

        return resolved

    def build_graph_payload(
        self,
        symbol_db_map: Optional[Dict[str, str]] = None,
        dependencies: Optional[List[ResolvedDependency]] = None,
    ) -> Dict[str, Any]:
        """
        Build React Flow compatible JSON payload with styled nodes and directed edges.
        """
        if dependencies is None:
            dependencies = self.resolve_dependencies(symbol_db_map=symbol_db_map)

        nodes = []
        edges = []

        # 1. Create Nodes from all extracted symbols
        for fqn, sym in self.fqn_index.items():
            sym_id = symbol_db_map.get(fqn, fqn) if symbol_db_map else fqn
            nodes.append({
                "id": sym_id,
                "fqn": fqn,
                "label": sym.name,
                "kind": sym.kind,
                "filePath": sym.file_path or "",
                "lineRange": [sym.start_line, sym.end_line],
                "signature": sym.signature or "",
                "docstring": sym.docstring or "",
                "metadata": sym.metadata,
            })

        # 2. Create Directed Edges from resolved dependencies
        for idx, dep in enumerate(dependencies):
            source_id = dep.caller_symbol_id or dep.caller_fqn
            target_id = dep.callee_symbol_id or dep.callee_fqn

            edges.append({
                "id": f"edge-{idx}-{source_id}-{target_id}",
                "source": source_id,
                "target": target_id,
                "type": dep.dependency_type,
                "label": dep.dependency_type,
                "lineNumber": dep.line_number,
                "filePath": dep.file_path,
            })

        return {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "nodes": nodes,
            "edges": edges,
        }
