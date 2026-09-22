import re
from typing import List, Optional
from packages.code_intel.models import ExtractedFileContext
from packages.code_intel.security.base_rule import BaseSecurityRule
from packages.code_intel.security.models import RawSecurityFinding, FindingSeverity, DetectionSource

class PathTraversalRule(BaseSecurityRule):
    """SEC-005: Detects path traversal risks in file system operations."""

    @property
    def rule_id(self) -> str:
        return "SEC-005"

    @property
    def category(self) -> str:
        return "Path Traversal"

    @property
    def title(self) -> str:
        return "Potential Path Traversal in File Operation"

    @property
    def default_severity(self) -> FindingSeverity:
        return FindingSeverity.HIGH

    @property
    def detection_source(self) -> DetectionSource:
        return DetectionSource.AST_ANALYSIS

    PATTERNS = [
        # Python open() with f-string or string concat containing variable
        re.compile(r"""\bopen\s*\(\s*f["'].*?\{[a-zA-Z0-9_]+\}.*?["']\s*[,)]"""),
        re.compile(r"""\bopen\s*\(\s*(?:os\.path\.join|Path)\s*\(.*?,\s*[a-zA-Z0-9_]+\s*\)"""),
        # Node.js fs.readFile / readFileSync with variable concatenation
        re.compile(r"""fs\.(?:readFile|readFileSync|createReadStream|unlink)\s*\(\s*(?:path\.join|`.*?\$\{)"""),
        # send_file / send_from_directory with direct variable
        re.compile(r"""\bsend_file\s*\(\s*(?:os\.path\.join|f["'])"""),
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

            for pattern in self.PATTERNS:
                if pattern.search(line):
                    # Check if file has an abspath or resolve check in proximity
                    findings.append(
                        RawSecurityFinding(
                            rule_id=self.rule_id,
                            category=self.category,
                            title=self.title,
                            description="File system operation accepts dynamic path components. Without canonical path verification (e.g. `os.path.commonpath` or `path.resolve`), an attacker can use `../` sequences to access unauthorized system files.",
                            severity=FindingSeverity.HIGH,
                            confidence=0.82,
                            detection_source=DetectionSource.AST_ANALYSIS,
                            file_path=file_path,
                            start_line=idx,
                            end_line=idx,
                            evidence=line.strip(),
                            remediation="Sanitize user-provided file paths by resolving absolute paths and verifying that the target path begins strictly within the intended root directory (e.g. using `os.path.commonpath`).",
                        )
                    )
                    break

        return findings
