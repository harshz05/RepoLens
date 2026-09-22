import re
from typing import List, Optional
from packages.code_intel.models import ExtractedFileContext
from packages.code_intel.security.base_rule import BaseSecurityRule
from packages.code_intel.security.models import RawSecurityFinding, FindingSeverity, DetectionSource

class InsecureCookieRule(BaseSecurityRule):
    """SEC-009: Detects insecure cookie and session attribute configurations."""

    @property
    def rule_id(self) -> str:
        return "SEC-009"

    @property
    def category(self) -> str:
        return "Session Security"

    @property
    def title(self) -> str:
        return "Insecure Cookie Configuration"

    @property
    def default_severity(self) -> FindingSeverity:
        return FindingSeverity.LOW

    @property
    def detection_source(self) -> DetectionSource:
        return DetectionSource.STATIC_RULE

    PATTERNS = [
        ("Explicit secure=False", re.compile(r"""set_cookie\s*\(.*?secure\s*=\s*False""", re.DOTALL), 0.90, FindingSeverity.MEDIUM),
        ("Explicit httponly=False", re.compile(r"""set_cookie\s*\(.*?httponly\s*=\s*False""", re.DOTALL), 0.90, FindingSeverity.MEDIUM),
        ("Node cookie without httpOnly/secure", re.compile(r"""res\.cookie\s*\(.*?\{\s*(?!.*httpOnly).*?\}""", re.DOTALL), 0.78, FindingSeverity.LOW),
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
            for name, pattern, confidence, severity in self.PATTERNS:
                if pattern.search(line):
                    findings.append(
                        RawSecurityFinding(
                            rule_id=self.rule_id,
                            category=self.category,
                            title=f"{self.title} ({name})",
                            description="Cookies transmitted without `secure=True` or `httponly=True` can be intercepted over unencrypted HTTP or accessed by malicious client-side JavaScript via XSS.",
                            severity=severity,
                            confidence=confidence,
                            detection_source=DetectionSource.STATIC_RULE,
                            file_path=file_path,
                            start_line=idx,
                            end_line=idx,
                            evidence=line.strip(),
                            remediation="Set `httponly=True`, `secure=True`, and `samesite='lax'` or `'strict'` on sensitive session and authentication cookies.",
                        )
                    )
                    break

        return findings
