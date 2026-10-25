import re
from typing import List, Optional
from packages.code_intel.models import ExtractedFileContext
from packages.code_intel.security.base_rule import BaseSecurityRule
from packages.code_intel.security.models import RawSecurityFinding, FindingSeverity, DetectionSource

class WeakCryptographyRule(BaseSecurityRule):
    """SEC-008: Detects weak or broken cryptographic hashing algorithms (MD5, SHA-1)."""

    @property
    def rule_id(self) -> str:
        return "SEC-008"

    @property
    def category(self) -> str:
        return "Cryptography"

    @property
    def title(self) -> str:
        return "Use of Broken or Weak Cryptographic Hash"

    @property
    def default_severity(self) -> FindingSeverity:
        return FindingSeverity.MEDIUM

    @property
    def detection_source(self) -> DetectionSource:
        return DetectionSource.STATIC_RULE

    PATTERNS = [
        ("Python hashlib.md5", re.compile(r"""\bhashlib\.md5\s*\((?!.*usedforsecurity\s*=\s*False)"""), 0.88),
        ("Python hashlib.sha1", re.compile(r"""\bhashlib\.sha1\s*\((?!.*usedforsecurity\s*=\s*False)"""), 0.85),
        ("Node crypto MD5/SHA1", re.compile(r"""crypto\.createHash\s*\(\s*["'](?:md5|sha1)["']\s*\)"""), 0.88),
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

            for name, pattern, confidence in self.PATTERNS:
                if pattern.search(line):
                    findings.append(
                        RawSecurityFinding(
                            rule_id=self.rule_id,
                            category=self.category,
                            title=f"{self.title} ({name})",
                            description="MD5 and SHA-1 have known collision vulnerabilities and should not be used for security-critical contexts (integrity verification, token signing, or password storage).",
                            severity=FindingSeverity.MEDIUM,
                            confidence=confidence,
                            detection_source=DetectionSource.STATIC_RULE,
                            file_path=file_path,
                            start_line=idx,
                            end_line=idx,
                            evidence=line.strip(),
                            remediation="Upgrade to SHA-256 (`hashlib.sha256`), SHA-512, or specialized password hashing functions (bcrypt, argon2) if hashing passwords.",
                        )
                    )
                    break

        return findings