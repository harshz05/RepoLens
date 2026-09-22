import re
import math
from typing import List, Optional
from packages.code_intel.models import ExtractedFileContext
from packages.code_intel.security.base_rule import BaseSecurityRule
from packages.code_intel.security.models import RawSecurityFinding, FindingSeverity, DetectionSource
from packages.code_intel.security.redactor import SecretRedactor

def shannon_entropy(data: str) -> float:
    """Calculate the Shannon entropy of a string."""
    if not data:
        return 0.0
    entropy = 0.0
    length = len(data)
    frequencies = {}
    for char in data:
        frequencies[char] = frequencies.get(char, 0) + 1
    for count in frequencies.values():
        p_x = count / length
        if p_x > 0:
            entropy -= p_x * math.log2(p_x)
    return entropy

class SecretsRule(BaseSecurityRule):
    """SEC-001: Detects hardcoded API keys, access tokens, and credentials."""

    @property
    def rule_id(self) -> str:
        return "SEC-001"

    @property
    def category(self) -> str:
        return "Secrets"

    @property
    def title(self) -> str:
        return "Potential Hardcoded Secret or API Credential"

    @property
    def default_severity(self) -> FindingSeverity:
        return FindingSeverity.HIGH

    @property
    def detection_source(self) -> DetectionSource:
        return DetectionSource.STATIC_RULE

    PATTERNS = [
        ("AWS Access Key", re.compile(r"""(?<![A-Z0-9])(AKIA[0-9A-Z]{16})(?![A-Z0-9])"""), 0.98, FindingSeverity.CRITICAL),
        ("GitHub Personal Access Token", re.compile(r"""(ghp_[0-9a-zA-Z]{36}|github_pat_[0-9a-zA-Z_]{82})"""), 0.98, FindingSeverity.CRITICAL),
        ("Slack Token", re.compile(r"""(xox[baprs]-[0-9a-zA-Z]{10,48})"""), 0.95, FindingSeverity.HIGH),
        ("Stripe Secret Key", re.compile(r"""(sk_live_[0-9a-zA-Z]{24})"""), 0.98, FindingSeverity.CRITICAL),
        ("Generic Private Key", re.compile(r"""(-----BEGIN[ A-Z0-9_-]+PRIVATE KEY-----)"""), 0.99, FindingSeverity.CRITICAL),
        ("High-Entropy Secret Assignment", re.compile(r"""(?:secret|password|api_key|apikey|token|auth_key)\s*[:=]\s*["']([^"'\s]{10,})["']""", re.IGNORECASE), 0.75, FindingSeverity.HIGH),
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

        for line_idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                # Skip comments unless private key
                if "-----BEGIN" not in line:
                    continue

            for name, pattern, confidence, severity in self.PATTERNS:
                match = pattern.search(line)
                if match:
                    secret_val = match.group(1)

                    # For generic high-entropy assignment, verify entropy to avoid false positives on dummy text
                    if name == "High-Entropy Secret Assignment":
                        if secret_val.lower() in ("placeholder", "changeme", "your_api_key_here", "example", "secret", "password"):
                            continue
                        ent = shannon_entropy(secret_val)
                        if ent < 3.0:
                            continue  # Low randomness -> likely a test constant or word

                    redacted_line = SecretRedactor.redact_text(line.strip())

                    findings.append(
                        RawSecurityFinding(
                            rule_id=self.rule_id,
                            category=self.category,
                            title=f"{self.title} ({name})",
                            description=f"Identified suspicious static credential or token pattern ({name}).",
                            severity=severity,
                            confidence=confidence,
                            detection_source=self.detection_source,
                            file_path=file_path,
                            start_line=line_idx,
                            end_line=line_idx,
                            evidence=redacted_line,
                            remediation="Move credential to an environment variable, secret store (e.g. AWS Secrets Manager, Vault), or runtime configuration. Never commit secrets to source control.",
                        )
                    )
                    break  # One finding per line is sufficient

        return findings
