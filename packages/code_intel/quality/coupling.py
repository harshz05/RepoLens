from typing import List, Dict, Set, Tuple
from packages.code_intel.models import ExtractedSymbol, ResolvedDependency
from packages.code_intel.quality.metrics import QualityFindingData

class CouplingAnalyzer:
    """
    Analyzes architectural coupling, fan-in / fan-out, circular dependencies,
    and dead-looking unreferenced internal symbols.
    """

    @classmethod
    def detect_circular_dependencies(
        cls,
        dependencies: List[ResolvedDependency],
    ) -> List[List[str]]:
        """
        Detects circular module dependency cycles using Tarjan's Strongly Connected Components.
        Returns list of cycles, where each cycle is a list of file paths.
        """
        # Build file-level directed graph
        adj: Dict[str, Set[str]] = {}
        all_nodes: Set[str] = set()

        for dep in dependencies:
            if not dep.file_path:
                continue
            src = dep.file_path
            all_nodes.add(src)
            if src not in adj:
                adj[src] = set()

            # Target file
            target_file = dep.callee_fqn.split("::")[0] if "::" in dep.callee_fqn else None
            if target_file and target_file != src:
                all_nodes.add(target_file)
                adj[src].add(target_file)

        # Tarjan's SCC Algorithm
        index = 0
        indices: Dict[str, int] = {}
        lowlinks: Dict[str, int] = {}
        on_stack: Set[str] = set()
        stack: List[str] = []
        sccs: List[List[str]] = []

        def strongconnect(node: str):
            nonlocal index
            indices[node] = index
            lowlinks[node] = index
            index += 1
            stack.append(node)
            on_stack.add(node)

            for neighbor in adj.get(node, ()):
                if neighbor not in indices:
                    strongconnect(neighbor)
                    lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
                elif neighbor in on_stack:
                    lowlinks[node] = min(lowlinks[node], indices[neighbor])

            if lowlinks[node] == indices[node]:
                scc = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    scc.append(w)
                    if w == node:
                        break
                if len(scc) > 1:
                    sccs.append(scc)

        for node in all_nodes:
            if node not in indices:
                strongconnect(node)

        return sccs

    @classmethod
    def analyze_symbol_coupling(
        cls,
        symbols: List[ExtractedSymbol],
        dependencies: List[ResolvedDependency],
    ) -> Tuple[List[QualityFindingData], Dict[str, Dict[str, float]]]:
        """
        Computes fan-in, fan-out, and instability per symbol.
        Returns:
            - List of quality findings (excessive coupling, dead symbols, circular dependencies)
            - Coupling metrics dictionary: {symbol_fqn: {"fan_in": X, "fan_out": Y, "instability": Z}}
        """
        findings: List[QualityFindingData] = []
        metrics: Dict[str, Dict[str, float]] = {}

        fan_in: Dict[str, int] = {s.fully_qualified_name: 0 for s in symbols}
        fan_out: Dict[str, int] = {s.fully_qualified_name: 0 for s in symbols}

        for dep in dependencies:
            if dep.caller_fqn in fan_out:
                fan_out[dep.caller_fqn] += 1
            if dep.callee_fqn in fan_in:
                fan_in[dep.callee_fqn] += 1

        for sym in symbols:
            fqn = sym.fully_qualified_name
            fi = fan_in.get(fqn, 0)
            fo = fan_out.get(fqn, 0)
            total = fi + fo
            instability = (fo / total) if total > 0 else 0.0

            metrics[fqn] = {
                "fan_in": float(fi),
                "fan_out": float(fo),
                "instability": round(instability, 2),
            }

            # 1. Excessive Fan-Out (Coupling)
            if fo > 12:
                findings.append(
                    QualityFindingData(
                        rule_id="QUAL-005",
                        metric_name="high_fan_out",
                        title="Excessive Symbol Coupling (High Fan-Out)",
                        description=f"Symbol '{sym.name}' depends directly on {fo} other symbols (threshold: 12). High fan-out indicates tight architectural coupling.",
                        severity="MEDIUM" if fo < 20 else "HIGH",
                        confidence=0.90,
                        value=float(fo),
                        threshold=12.0,
                        file_path=sym.file_path or "",
                        start_line=sym.start_line,
                        end_line=sym.end_line,
                        recommendation="Introduce facade services or decouple responsibilities via dependency inversion.",
                        symbol_fqn=fqn,
                    )
                )

            # 2. Dead-Looking Internal Symbol (0 incoming callers)
            # Exclude API routes, entrypoints, and class constructors (__init__)
            is_entrypoint = sym.kind == "api_endpoint" or (sym.metadata and "route" in sym.metadata)
            is_special = sym.name.startswith("__") or sym.name in ("main", "handler")

            if sym.kind in ("function", "method") and fi == 0 and not is_entrypoint and not is_special:
                findings.append(
                    QualityFindingData(
                        rule_id="QUAL-007",
                        metric_name="dead_code_candidate",
                        title="Potentially Unused Internal Function",
                        description=f"Function '{sym.name}' has 0 recorded callers across the repository.",
                        severity="INFO",
                        confidence=0.65,  # Heuristic confidence
                        value=0.0,
                        threshold=1.0,
                        file_path=sym.file_path or "",
                        start_line=sym.start_line,
                        end_line=sym.end_line,
                        recommendation="Verify whether this function is dead code or exposed via external public interfaces. If unused, remove to reduce maintenance overhead.",
                        symbol_fqn=fqn,
                    )
                )

        # 3. Circular Dependencies across files
        cycles = cls.detect_circular_dependencies(dependencies)
        for cycle in cycles:
            cycle_str = " ➔ ".join(cycle) + f" ➔ {cycle[0]}"
            findings.append(
                QualityFindingData(
                    rule_id="QUAL-006",
                    metric_name="circular_dependency",
                    title="Circular Module Dependency Detected",
                    description=f"Circular dependency cycle detected across {len(cycle)} files: {cycle_str}",
                    severity="HIGH",
                    confidence=0.95,
                    value=float(len(cycle)),
                    threshold=0.0,
                    file_path=cycle[0],
                    start_line=1,
                    end_line=1,
                    recommendation="Break the dependency cycle by extracting shared data types/interfaces into a lower-level module.",
                )
            )

        return findings, metrics
