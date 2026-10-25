import re
from typing import List, Optional
from packages.code_intel.models import ExtractedFileContext
from packages.code_intel.security.base_rule import BaseSecurityRule, iter_logical_lines, compact_evidence
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
        ("Node cookie without httpOnly", re.compile(r"""res\.cookie\s*\((?!.*httpOnly\s*:\s*true).*\)"""), 0.78, FindingSeverity.LOW),
    ]

    def analyze_file(
        self,
        code_text: str,
        file_path: str,
        language: str,
        context: Optional[ExtractedFileContext] = None,
    ) -> List[RawSecurityFinding]:
        findings: List[RawSecurityFinding] = []

        # Logical lines: set_cookie(...) / res.cookie(...) calls often span several lines.
        for start, end, text in iter_logical_lines(code_text):
            for name, pattern, confidence, severity in self.PATTERNS:
                if pattern.search(text):
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
                            start_line=start,
                            end_line=end,
                            evidence=compact_evidence(text),
                            remediation="Set `httponly=True`, `secure=True`, and `samesite='lax'` or `'strict'` on sensitive session and authentication cookies.",
                        )
                    )
                    break

        return findings