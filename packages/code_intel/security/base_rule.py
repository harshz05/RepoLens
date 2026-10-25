from abc import ABC, abstractmethod
from typing import Iterator, List, Optional, Tuple
from packages.code_intel.models import ExtractedFileContext
from packages.code_intel.security.models import RawSecurityFinding, FindingSeverity, DetectionSource


def iter_logical_lines(code_text: str, max_span: int = 12) -> Iterator[Tuple[int, int, str]]:
    """
    Yield (start_line, end_line, text) for each *logical* line.

    A logical line joins physical lines while parentheses/brackets are unbalanced, so a call
    spread over several lines (e.g. `subprocess.run(\n cmd,\n shell=True\n)`) is matched as one
    statement. Comment-only lines are skipped. `max_span` bounds the join so an unbalanced
    bracket (or one inside a string) can never swallow the rest of the file.
    """
    lines = code_text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            i += 1
            continue

        start = i
        buf = [stripped]
        depth = raw.count("(") + raw.count("[") + raw.count("{") - raw.count(")") - raw.count("]") - raw.count("}")
        while depth > 0 and i + 1 < n and (i - start) < max_span:
            i += 1
            nxt = lines[i]
            buf.append(nxt.strip())
            depth += nxt.count("(") + nxt.count("[") + nxt.count("{") - nxt.count(")") - nxt.count("]") - nxt.count("}")
        yield start + 1, i + 1, " ".join(buf)
        i += 1


def compact_evidence(text: str, limit: int = 300) -> str:
    """Collapse whitespace and truncate evidence snippets."""
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 3] + "..."


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
        """Detection methodology (STATIC_RULE = pattern match, AST_ANALYSIS = tree-sitter derived, GRAPH_ANALYSIS)."""
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