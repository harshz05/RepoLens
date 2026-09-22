import re
from typing import List, Optional
from packages.code_intel.models import ExtractedFileContext
from packages.code_intel.security.base_rule import BaseSecurityRule
from packages.code_intel.security.models import RawSecurityFinding, FindingSeverity, DetectionSource

class PermissiveCORSRule(BaseSecurityRule):
    """SEC-007: Detects overly permissive CORS policies combined with credentials."""

    @property
    def rule_id(self) -> str:
        return "SEC-007"

    @property
    def category(self) -> str:
        return "CORS Misconfiguration"

    @property
    def title(self) -> str:
        return "Permissive CORS Policy with Credentials"

    @property
    def default_severity(self) -> FindingSeverity:
        return FindingSeverity.MEDIUM

    @property
    def detection_source(self) -> DetectionSource:
        return DetectionSource.STATIC_RULE

    PATTERNS = [
        re.compile(r"""allow_origins\s*=\s*\[\s*["']\*["']\s*\].*?allow_credentials\s*=\s*True""", re.DOTALL),
        re.compile(r"""allow_credentials\s*=\s*True.*?allow_origins\s*=\s*\[\s*["']\*["']\s*\]""", re.DOTALL),
        re.compile(r"""origin\s*:\s*["']\*["'].*?credentials\s*:\s*true""", re.DOTALL),
    ]

    def analyze_file(
        self,
        code_text: str,
        file_path: str,
        language: str,
        context: Optional[ExtractedFileContext] = None,
    ) -> List[RawSecurityFinding]:
        findings: List[RawSecurityFinding] = []

        for pattern in self.PATTERNS:
            match = pattern.search(code_text)
            if match:
                # Find line number of match
                start_char = match.start()
                line_no = code_text[:start_char].count("\n") + 1

                findings.append(
                    RawSecurityFinding(
                        rule_id=self.rule_id,
                        category=self.category,
                        title=self.title,
                        description="Wildcard CORS origin ('*') combined with credential support enables cross-site request forgery and unauthorized data exfiltration across origins.",
                        severity=FindingSeverity.HIGH,
                        confidence=0.90,
                        detection_source=DetectionSource.STATIC_RULE,
                        file_path=file_path,
                        start_line=line_no,
                        end_line=line_no,
                        evidence=match.group(0)[:150].replace("\n", " ").strip(),
                        remediation="Explicitly specify trusted origin domains in `allow_origins` instead of wildcard `*` when `allow_credentials=True` is enabled.",
                    )
                )
                break

        return findings
