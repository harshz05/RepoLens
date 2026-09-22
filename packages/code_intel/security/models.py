from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any

class FindingSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

class DetectionSource(str, Enum):
    STATIC_RULE = "STATIC_RULE"
    AST_ANALYSIS = "AST_ANALYSIS"
    GRAPH_ANALYSIS = "GRAPH_ANALYSIS"
    AI_ANALYSIS = "AI_ANALYSIS"

@dataclass
class RawSecurityFinding:
    rule_id: str
    category: str
    title: str
    description: str
    severity: FindingSeverity
    confidence: float  # 0.0 - 1.0
    detection_source: DetectionSource
    file_path: str
    start_line: int
    end_line: int
    evidence: str
    remediation: str
    symbol_fqn: Optional[str] = None
    graph_reachability_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_ai_assisted: bool = False
