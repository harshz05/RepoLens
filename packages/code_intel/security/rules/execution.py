import re
from typing import List, Optional
from packages.code_intel.models import ExtractedFileContext
from packages.code_intel.security.base_rule import BaseSecurityRule
from packages.code_intel.security.models import RawSecurityFinding, FindingSeverity, DetectionSource

class DynamicExecutionRule(BaseSecurityRule):
    """SEC-002: Detects dangerous dynamic execution functions (eval, exec, Function)."""

    @property
    def rule_id(self) -> str:
        return "SEC-002"

    @property
    def category(self) -> str:
        return "Dynamic Execution"

    @property
    def title(self) -> str:
        return "Dangerous Dynamic Code Execution"

    @property
    def default_severity(self) -> FindingSeverity:
        return FindingSeverity.HIGH

    @property
    def detection_source(self) -> DetectionSource:
        return DetectionSource.AST_ANALYSIS

    DANGEROUS_CALLS = {
        "python": {"eval", "exec"},
        "typescript": {"eval", "Function", "runInThisContext", "runInNewContext"},
        "javascript": {"eval", "Function", "runInThisContext", "runInNewContext"},
    }

    PATTERNS = [
        re.compile(r"""\b(eval|exec)\s*\((.*?)\)"""),
        re.compile(r"""\bnew\s+Function\s*\((.*?)\)"""),
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

        # 1. Inspect AST extracted calls if available
        matched_lines = set()
        if context:
            lang_key = "python" if "python" in language.lower() else "typescript"
            dangerous_names = self.DANGEROUS_CALLS.get(lang_key, {"eval", "exec"})

            for call in context.calls:
                if call.callee_name in dangerous_names:
                    line_no = call.line_number
                    matched_lines.add(line_no)
                    snippet = lines[line_no - 1].strip() if 0 < line_no <= len(lines) else f"{call.callee_name}(...)"

                    findings.append(
                        RawSecurityFinding(
                            rule_id=self.rule_id,
                            category=self.category,
                            title=f"{self.title} ({call.callee_name})",
                            description=f"Invocation of dynamic code execution function '{call.callee_name}'. If arguments contain untrusted user input, this enables arbitrary Remote Code Execution (RCE).",
                            severity=FindingSeverity.CRITICAL if call.callee_name in ("eval", "exec") else FindingSeverity.HIGH,
                            confidence=0.92,
                            detection_source=DetectionSource.AST_ANALYSIS,
                            file_path=file_path,
                            start_line=line_no,
                            end_line=line_no,
                            evidence=snippet,
                            remediation="Refactor to use deterministic parsing (e.g. ast.literal_eval, JSON.parse) or a safe lookup map rather than dynamically evaluating code.",
                            symbol_fqn=call.caller_fqn,
                        )
                    )

        # 2. Regex fallback for lines not captured by AST call visitor
        for idx, line in enumerate(lines, start=1):
            if idx in matched_lines:
                continue
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            for pattern in self.PATTERNS:
                match = pattern.search(line)
                if match:
                    func_name = match.group(1) if match.lastindex and match.lastindex >= 1 else "eval"
                    findings.append(
                        RawSecurityFinding(
                            rule_id=self.rule_id,
                            category=self.category,
                            title=f"{self.title} ({func_name})",
                            description=f"Invocation of dynamic code execution function '{func_name}'.",
                            severity=FindingSeverity.HIGH,
                            confidence=0.88,
                            detection_source=DetectionSource.STATIC_RULE,
                            file_path=file_path,
                            start_line=idx,
                            end_line=idx,
                            evidence=line.strip(),
                            remediation="Avoid dynamic code evaluation. Use static data structures, serialization formats (JSON), or domain-specific parsers.",
                        )
                    )
                    break

        return findings
