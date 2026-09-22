import re
from typing import List, Optional
from packages.code_intel.models import ExtractedFileContext
from packages.code_intel.security.base_rule import BaseSecurityRule
from packages.code_intel.security.models import RawSecurityFinding, FindingSeverity, DetectionSource

class DeserializationRule(BaseSecurityRule):
    """SEC-006: Detects insecure deserialization mechanisms (pickle, unsafe yaml, marshal)."""

    @property
    def rule_id(self) -> str:
        return "SEC-006"

    @property
    def category(self) -> str:
        return "Insecure Deserialization"

    @property
    def title(self) -> str:
        return "Insecure Object Deserialization"

    @property
    def default_severity(self) -> FindingSeverity:
        return FindingSeverity.CRITICAL

    @property
    def detection_source(self) -> DetectionSource:
        return DetectionSource.AST_ANALYSIS

    PATTERNS = [
        ("Python Pickle Deserialization", re.compile(r"""\b(?:pickle|_pickle|cPickle)\.(?:loads?|Unpickler)\b"""), 0.96, FindingSeverity.CRITICAL),
        ("Unsafe YAML Load", re.compile(r"""\byaml\.load\s*\((?!.*Loader\s*=\s*(?:yaml\.)?SafeLoader)"""), 0.92, FindingSeverity.HIGH),
        ("Python Marshal Deserialization", re.compile(r"""\bmarshal\.loads?\b"""), 0.90, FindingSeverity.HIGH),
    ]

    def analyze_file(
        self,
        code_text: str,
        file_path: str,
        language: str,
        context: Optional[ExtractedFileContext] = None,
    ) -> List[RawSecurityFinding]:
        findings: List[RawSecurityFinding] = []
        lines = code_text.splitlines()

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            for name, pattern, confidence, severity in self.PATTERNS:
                if pattern.search(line):
                    findings.append(
                        RawSecurityFinding(
                            rule_id=self.rule_id,
                            category=self.category,
                            title=f"{self.title} ({name})",
                            description=f"Insecure deserialization function '{name}' detected. Deserializing untrusted data with pickle or unsafe loaders can trigger arbitrary code execution during object reconstitution.",
                            severity=severity,
                            confidence=confidence,
                            detection_source=DetectionSource.AST_ANALYSIS,
                            file_path=file_path,
                            start_line=idx,
                            end_line=idx,
                            evidence=line.strip(),
                            remediation="Avoid pickle/unsafe YAML for untrusted data. Use safe, language-neutral serialization formats such as JSON or Protocol Buffers, or enforce `yaml.safe_load()`.",
                        )
                    )
                    break

        return findings
