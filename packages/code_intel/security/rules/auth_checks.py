import re
from typing import List, Optional
from packages.code_intel.models import ExtractedFileContext
from packages.code_intel.parsers.route_utils import extract_route_info
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

    # Evidence that access control is wired in. Deliberately specific: bare words like "user"
    # or "admin" are NOT used because they match ordinary parameter/function names.
    AUTH_MARKERS = (
        "auth", "token", "permission", "security", "jwt", "session",
        "current_user", "get_user", "login_required", "requires", "oauth", "bearer", "api_key",
    )

    @classmethod
    def _has_auth_evidence(cls, signature: str, decorators: List[str]) -> bool:
        # Only the parameter list: the function NAME must not count as evidence.
        params = signature[signature.find("("):] if "(" in signature else ""
        # Exclude the route decorator itself (its path, e.g. "/admin/x", is not an auth marker).
        other_decorators = [d for d in decorators if extract_route_info(str(d)) is None]
        haystack = f"{params} {' '.join(str(d) for d in other_decorators)}".lower()
        return any(marker in haystack for marker in cls.AUTH_MARKERS)

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
            if sym.kind != "api_endpoint":
                continue
            meta = sym.metadata or {}
            route = meta.get("route", "")
            if not route or not self.SENSITIVE_PATH_PATTERNS.search(route):
                continue

            if self._has_auth_evidence(sym.signature or "", list(meta.get("decorators", []))):
                continue

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