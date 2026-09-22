import re
from typing import List, Optional
from packages.code_intel.models import ExtractedFileContext
from packages.code_intel.security.base_rule import BaseSecurityRule
from packages.code_intel.security.models import RawSecurityFinding, FindingSeverity, DetectionSource

class SubprocessRule(BaseSecurityRule):
    """SEC-003: Detects unsafe subprocess spawning and shell command execution."""

    @property
    def rule_id(self) -> str:
        return "SEC-003"

    @property
    def category(self) -> str:
        return "Command Injection"

    @property
    def title(self) -> str:
        return "Unsafe Subprocess or Shell Execution"

    @property
    def default_severity(self) -> FindingSeverity:
        return FindingSeverity.HIGH

    @property
    def detection_source(self) -> DetectionSource:
        return DetectionSource.AST_ANALYSIS

    PATTERNS = [
        ("Subprocess with shell=True", re.compile(r"""subprocess\.(?:Popen|run|call|check_output|check_call)\s*\(.*shell\s*=\s*True""", re.DOTALL), 0.95, FindingSeverity.HIGH),
        ("Unsafe os.system", re.compile(r"""\bos\.system\s*\((.*?)\)"""), 0.90, FindingSeverity.HIGH),
        ("Unsafe os.popen", re.compile(r"""\bos\.popen\s*\((.*?)\)"""), 0.88, FindingSeverity.MEDIUM),
        ("Node child_process.exec", re.compile(r"""child_process\.(?:exec|execSync)\s*\((.*?)\)"""), 0.90, FindingSeverity.HIGH),
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
                    # Check if line contains variable interpolation (e.g. f-string, format, or +)
                    has_interpolation = any(sym in line for sym in ("f\"", "f'", "%", ".format(", "+", "$", "`"))
                    final_sev = FindingSeverity.CRITICAL if has_interpolation and severity == FindingSeverity.HIGH else severity
                    final_conf = min(0.98, confidence + 0.05) if has_interpolation else confidence

                    findings.append(
                        RawSecurityFinding(
                            rule_id=self.rule_id,
                            category=self.category,
                            title=f"{self.title} ({name})",
                            description=f"Detected shell execution command '{name}'. Executing command strings through a shell creates critical command injection risks if user-controllable input reaches arguments.",
                            severity=final_sev,
                            confidence=final_conf,
                            detection_source=DetectionSource.AST_ANALYSIS,
                            file_path=file_path,
                            start_line=idx,
                            end_line=idx,
                            evidence=line.strip(),
                            remediation="Pass command arguments as an array of arguments without a shell (e.g. `subprocess.run(['cmd', arg], shell=False)` or `child_process.execFile`). Avoid invoking the shell interpreter directly.",
                        )
                    )
                    break

        return findings
