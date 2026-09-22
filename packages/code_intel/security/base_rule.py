from abc import ABC, abstractmethod
from typing import List, Optional
from packages.code_intel.models import ExtractedFileContext
from packages.code_intel.security.models import RawSecurityFinding, FindingSeverity, DetectionSource

class BaseSecurityRule(ABC):
    """Abstract base class for all modular security detection rules."""

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Unique identifier (e.g. 'SEC-001')."""
        pass

    @property
    @abstractmethod
    def category(self) -> str:
        """Category name (e.g. 'Secrets', 'Injection', 'Execution', 'Cryptography')."""
        pass

    @property
    @abstractmethod
    def title(self) -> str:
        """Human-readable finding title."""
        pass

    @property
    @abstractmethod
    def default_severity(self) -> FindingSeverity:
        """Default severity level."""
        pass

    @property
    @abstractmethod
    def detection_source(self) -> DetectionSource:
        """Detection methodology (STATIC_RULE, AST_ANALYSIS, GRAPH_ANALYSIS)."""
        pass

    @abstractmethod
    def analyze_file(
        self,
        code_text: str,
        file_path: str,
        language: str,
        context: Optional[ExtractedFileContext] = None,
    ) -> List[RawSecurityFinding]:
        """
        Analyze file text and/or extracted AST context and return identified findings.
        """
        pass
