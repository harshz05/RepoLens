import re
from typing import List, Optional
from packages.code_intel.models import ExtractedFileContext
from packages.code_intel.security.base_rule import BaseSecurityRule
from packages.code_intel.security.models import RawSecurityFinding, FindingSeverity, DetectionSource

class MissingAuthCheckRule(BaseSecurityRule):
    """SEC-010: Detects potentially unauthenticated sensitive or administrative API endpoints."""

    @property
    def rule_id(self) -> str:
        return "SEC-010"

    @property
    def category(self) -> str:
        return "Authentication"

    @property
    def title(self) -> str:
        return "Potentially Unprotected Sensitive API Endpoint"

    @property
    def default_severity(self) -> FindingSeverity:
        return FindingSeverity.MEDIUM

    @property
    def detection_source(self) -> DetectionSource:
        return DetectionSource.AST_ANALYSIS

    SENSITIVE_PATH_PATTERNS = re.compile(r"""(?:admin|internal|manage|delete|reset|superuser|dashboard)""", re.IGNORECASE)

    def analyze_file(
        self,
        code_text: str,
        file_path: str,
        language: str,
        context: Optional[ExtractedFileContext] = None,
    ) -> List[RawSecurityFinding]:
        findings: List[RawSecurityFinding] = []
        if not context:
            return findings

        for sym in context.symbols:
            if sym.kind == "api_endpoint":
                meta = sym.metadata or {}
                route = meta.get("route", "")

                if self.SENSITIVE_PATH_PATTERNS.search(route):
                    # Check if signature or decorators contain auth dependencies
                    sig = sym.signature or ""
                    has_auth = any(
                        term in sig.lower()
                        for term in ("auth", "user", "token", "permission", "admin", "security", "jwt", "session")
                    )

                    if not has_auth:
                        findings.append(
                            RawSecurityFinding(
                                rule_id=self.rule_id,
                                category=self.category,
                                title=self.title,
                                description=f"API Endpoint '{route}' ({sym.name}) appears to perform administrative or sensitive actions without visible authentication or authorization dependencies.",
                                severity=FindingSeverity.MEDIUM,
                                confidence=0.72,  # Heuristic finding
                                detection_source=DetectionSource.AST_ANALYSIS,
                                file_path=file_path,
                                start_line=sym.start_line,
                                end_line=sym.end_line,
                                evidence=f"@{meta.get('http_method', 'ROUTE')}(\"{route}\") def {sym.name}{sym.signature or '()'}",
                                remediation="Verify endpoint access control. Ensure a security dependency (e.g. `Depends(get_current_admin)`) or authorization middleware is configured.",
                                symbol_fqn=sym.fully_qualified_name,
                            )
                        )

        return findings
