from typing import List, Dict, Set, Optional, Tuple
from packages.code_intel.models import ExtractedSymbol, ResolvedDependency
from packages.code_intel.security.models import RawSecurityFinding, FindingSeverity, DetectionSource

class GraphSecurityAnalyzer:
    """
    Evaluates reachability of potentially vulnerable sinks from public entrypoints
    using the static dependency call-graph.
    """

    MAX_TRAVERSAL_DEPTH = 4

    def __init__(
        self,
        symbols: List[ExtractedSymbol],
        dependencies: List[ResolvedDependency],
    ):
        self.symbols = symbols
        self.dependencies = dependencies
        self.symbol_by_fqn: Dict[str, ExtractedSymbol] = {s.fully_qualified_name: s for s in symbols}

        # Build forward adjacency list: caller -> list of callees
        self.adjacency: Dict[str, List[str]] = {}
        for dep in dependencies:
            if dep.caller_fqn and dep.callee_fqn:
                if dep.caller_fqn not in self.adjacency:
                    self.adjacency[dep.caller_fqn] = []
                self.adjacency[dep.caller_fqn].append(dep.callee_fqn)

        # Build reverse adjacency list: callee -> list of callers
        self.reverse_adjacency: Dict[str, List[str]] = {}
        for dep in dependencies:
            if dep.caller_fqn and dep.callee_fqn:
                if dep.callee_fqn not in self.reverse_adjacency:
                    self.reverse_adjacency[dep.callee_fqn] = []
                self.reverse_adjacency[dep.callee_fqn].append(dep.caller_fqn)

        # Identify entrypoints (API endpoints or top-level public functions)
        self.entrypoints: Set[str] = set()
        for sym in symbols:
            if sym.kind == "api_endpoint":
                self.entrypoints.add(sym.fully_qualified_name)
            elif sym.metadata and ("route" in sym.metadata or "http_method" in sym.metadata):
                self.entrypoints.add(sym.fully_qualified_name)

    def find_entrypoint_paths_to_symbol(self, target_fqn: str) -> List[List[str]]:
        """
        Reverse BFS/DFS from target sink symbol backwards to find any paths starting from an API entrypoint.
        Returns list of paths where path[0] is the entrypoint and path[-1] is target_fqn.
        """
        if not target_fqn or target_fqn not in self.symbol_by_fqn:
            return []

        # If target is itself an entrypoint
        if target_fqn in self.entrypoints:
            return [[target_fqn]]

        valid_paths: List[List[str]] = []
        queue: List[Tuple[str, List[str]]] = [(target_fqn, [target_fqn])]
        visited: Set[str] = {target_fqn}

        while queue:
            curr_sym, path = queue.pop(0)
            if len(path) > self.MAX_TRAVERSAL_DEPTH:
                continue

            callers = self.reverse_adjacency.get(curr_sym, [])
            for caller in callers:
                if caller in self.entrypoints:
                    full_path = [caller] + path
                    valid_paths.append(full_path)
                elif caller not in visited and len(path) < self.MAX_TRAVERSAL_DEPTH:
                    visited.add(caller)
                    queue.append((caller, [caller] + path))

        return valid_paths

    def find_symbol_for_line(self, file_path: str, line_no: int) -> Optional[ExtractedSymbol]:
        """Find the innermost symbol containing the specified file line."""
        matching = [
            s for s in self.symbols
            if s.file_path == file_path and s.start_line <= line_no <= s.end_line
        ]
        if not matching:
            return None
        # Return the smallest/innermost range
        matching.sort(key=lambda s: s.end_line - s.start_line)
        return matching[0]

    def enrich_findings_with_graph_context(
        self,
        findings: List[RawSecurityFinding],
    ) -> List[RawSecurityFinding]:
        """
        Correlate static findings with call-graph reachability.
        Elevates severity and annotates reachability paths when a sink is reachable from an API route.
        """
        enriched: List[RawSecurityFinding] = []

        for finding in findings:
            # 1. Determine containing symbol FQN
            sym_fqn = finding.symbol_fqn
            if not sym_fqn:
                contained_sym = self.find_symbol_for_line(finding.file_path, finding.start_line)
                if contained_sym:
                    sym_fqn = contained_sym.fully_qualified_name
                    finding.symbol_fqn = sym_fqn

            if not sym_fqn:
                enriched.append(finding)
                continue

            # 2. Check reachability from any public entrypoint
            paths = self.find_entrypoint_paths_to_symbol(sym_fqn)
            if paths:
                # Find shortest path
                paths.sort(key=len)
                best_path = paths[0]
                entrypoint_name = best_path[0].split("::")[-1]
                path_str = " ➔ ".join(p.split("::")[-1] for p in best_path)

                # Elevate severity if applicable
                elevated_sev = finding.severity
                if finding.severity == FindingSeverity.MEDIUM:
                    elevated_sev = FindingSeverity.HIGH
                elif finding.severity == FindingSeverity.HIGH:
                    elevated_sev = FindingSeverity.CRITICAL

                # Compute confidence adjusted for distance
                hop_count = len(best_path) - 1
                adjusted_conf = max(0.60, round(finding.confidence * (0.95 ** hop_count), 2))

                finding.severity = elevated_sev
                finding.confidence = adjusted_conf
                finding.detection_source = DetectionSource.GRAPH_ANALYSIS
                finding.graph_reachability_path = path_str
                finding.description += f" [Reachable from public entrypoint '{entrypoint_name}' via call path: {path_str}]"

            enriched.append(finding)

        return enriched
