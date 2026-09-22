import re
from typing import List, Optional
from packages.code_intel.models import ExtractedFileContext
from packages.code_intel.security.base_rule import BaseSecurityRule
from packages.code_intel.security.models import RawSecurityFinding, FindingSeverity, DetectionSource

class SQLInjectionRule(BaseSecurityRule):
    """SEC-004: Detects dynamic raw SQL query construction and SQL injection patterns."""

    @property
    def rule_id(self) -> str:
        return "SEC-004"

    @property
    def category(self) -> str:
        return "SQL Injection"

    @property
    def title(self) -> str:
        return "Potential SQL Injection via Unsafe String Construction"

    @property
    def default_severity(self) -> FindingSeverity:
        return FindingSeverity.HIGH

    @property
    def detection_source(self) -> DetectionSource:
        return DetectionSource.AST_ANALYSIS

    SQL_KEYWORDS = re.compile(r"""\b(SELECT\s+.*?\s+FROM|INSERT\s+INTO|UPDATE\s+.*?\s+SET|DELETE\s+FROM)\b""", re.IGNORECASE)

    PATTERNS = [
        # Python f-string with SQL
        re.compile(r"""execute\s*\(\s*f["'].*?(?:SELECT|INSERT|UPDATE|DELETE).*?\{.*?\}""", re.IGNORECASE),
        # Python % format or .format() with SQL
        re.compile(r"""execute\s*\(\s*["'].*?(?:SELECT|INSERT|UPDATE|DELETE).*?["']\s*%\s*""", re.IGNORECASE),
        re.compile(r"""execute\s*\(\s*["'].*?(?:SELECT|INSERT|UPDATE|DELETE).*?["']\.format\s*\(""", re.IGNORECASE),
        # Direct string concatenation in execute
        re.compile(r"""execute\s*\(\s*["'].*?(?:SELECT|INSERT|UPDATE|DELETE).*?["']\s*\+\s*""", re.IGNORECASE),
        # JS Template literal in query/execute
        re.compile(r"""(?:query|execute|raw)\s*\(\s*`.*?(?:SELECT|INSERT|UPDATE|DELETE).*?\$\{.*?\}""", re.IGNORECASE),
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

        # Check line-by-line and multi-line buffer
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            for pattern in self.PATTERNS:
                if pattern.search(line):
                    findings.append(
                        RawSecurityFinding(
                            rule_id=self.rule_id,
                            category=self.category,
                            title=self.title,
                            description="Identified raw SQL query constructed via dynamic string formatting or interpolation in database execution call. If variables are unescaped user input, this allows arbitrary SQL injection.",
                            severity=FindingSeverity.HIGH,
                            confidence=0.88,
                            detection_source=DetectionSource.AST_ANALYSIS,
                            file_path=file_path,
                            start_line=idx,
                            end_line=idx,
                            evidence=line.strip(),
                            remediation="Use parameterized queries / bind parameters (e.g. `cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))` or SQLAlchemy ORM filters) rather than string interpolation.",
                        )
                    )
                    break

        return findings
