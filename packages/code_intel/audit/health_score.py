from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from packages.code_intel.security.models import RawSecurityFinding, FindingSeverity
from packages.code_intel.quality.metrics import QualityFindingData

@dataclass
class HealthScoreBreakdown:
    overall_health: float
    security_score: float
    maintainability_score: float
    complexity_score: float
    coupling_score: float
    architecture_score: float
    dimensions_summary: Dict[str, Any]

class HealthScoreCalculator:
    """
    Computes a transparent, 5-dimensional repository health score matrix.
    Each dimension is normalized on a bounded 0.0 - 100.0 scale.
    """

    @classmethod
    def calculate(
        cls,
        total_loc: int,
        total_files: int,
        total_symbols: int,
        security_findings: List[RawSecurityFinding],
        quality_findings: List[QualityFindingData],
        coupling_metrics: Dict[str, Dict[str, float]],
        circular_cycles_count: int = 0,
    ) -> HealthScoreBreakdown:
        ksloc = max(0.5, total_loc / 1000.0)

        # 1. Security Score
        crit_count = sum(1 for f in security_findings if f.severity == FindingSeverity.CRITICAL)
        high_count = sum(1 for f in security_findings if f.severity == FindingSeverity.HIGH)
        med_count = sum(1 for f in security_findings if f.severity == FindingSeverity.MEDIUM)
        low_count = sum(1 for f in security_findings if f.severity == FindingSeverity.LOW)

        weighted_security_penalty = (crit_count * 15.0) + (high_count * 8.0) + (med_count * 3.0) + (low_count * 1.0)
        penalty_per_ksloc = (weighted_security_penalty / ksloc) * 8.0
        security_score = max(0.0, min(100.0, round(100.0 - penalty_per_ksloc, 1)))

        # 2. Maintainability Score
        large_files = sum(1 for f in quality_findings if f.metric_name == "large_file")
        large_funcs = sum(1 for f in quality_findings if f.metric_name == "large_function")
        maint_penalty = ((large_files * 8.0) + (large_funcs * 4.0)) / max(1.0, total_files) * 15.0
        maintainability_score = max(0.0, min(100.0, round(100.0 - maint_penalty, 1)))

        # 3. Complexity Score
        high_cc_funcs = sum(1 for f in quality_findings if f.metric_name == "cyclomatic_complexity")
        # Base on total symbols ratio
        complexity_penalty = (high_cc_funcs / max(1.0, total_symbols)) * 120.0
        complexity_score = max(0.0, min(100.0, round(100.0 - complexity_penalty, 1)))

        # 4. Coupling Score
        all_fan_outs = [m.get("fan_out", 0.0) for m in coupling_metrics.values()]
        avg_fan_out = (sum(all_fan_outs) / len(all_fan_outs)) if all_fan_outs else 0.0
        coupling_penalty = (circular_cycles_count * 25.0) + (max(0.0, avg_fan_out - 6.0) * 8.0)
        coupling_score = max(0.0, min(100.0, round(100.0 - coupling_penalty, 1)))

        # 5. Architecture Score
        arch_penalty = (circular_cycles_count * 30.0)
        architecture_score = max(0.0, min(100.0, round(100.0 - arch_penalty, 1)))

        # Weighted Overall Health
        overall_health = (
            0.30 * security_score
            + 0.20 * maintainability_score
            + 0.20 * complexity_score
            + 0.15 * coupling_score
            + 0.15 * architecture_score
        )
        overall_health = round(overall_health, 1)

        summary = {
            "critical_security_findings": crit_count,
            "high_security_findings": high_count,
            "medium_security_findings": med_count,
            "low_security_findings": low_count,
            "large_files_count": large_files,
            "large_functions_count": large_funcs,
            "high_complexity_functions": high_cc_funcs,
            "circular_dependency_cycles": circular_cycles_count,
            "average_fan_out": round(avg_fan_out, 2),
            "ksloc": round(ksloc, 2),
        }

        return HealthScoreBreakdown(
            overall_health=overall_health,
            security_score=security_score,
            maintainability_score=maintainability_score,
            complexity_score=complexity_score,
            coupling_score=coupling_score,
            architecture_score=architecture_score,
            dimensions_summary=summary,
        )
