from typing import List, Dict, Optional
from packages.code_intel.models import ExtractedFileContext
from packages.code_intel.security.base_rule import BaseSecurityRule
from packages.code_intel.security.models import RawSecurityFinding
from packages.code_intel.security.rules.secrets import SecretsRule
from packages.code_intel.security.rules.execution import DynamicExecutionRule
from packages.code_intel.security.rules.subprocesses import SubprocessRule
from packages.code_intel.security.rules.sql_injection import SQLInjectionRule
from packages.code_intel.security.rules.path_traversal import PathTraversalRule
from packages.code_intel.security.rules.deserialization import DeserializationRule
from packages.code_intel.security.rules.cors_config import PermissiveCORSRule
from packages.code_intel.security.rules.crypto import WeakCryptographyRule
from packages.code_intel.security.rules.cookie_session import InsecureCookieRule
from packages.code_intel.security.rules.auth_checks import MissingAuthCheckRule

class SecurityRuleRegistry:
    """Central registry for all active security rules."""

    def __init__(self):
        self._rules: Dict[str, BaseSecurityRule] = {}
        self.register_defaults()

    def register(self, rule: BaseSecurityRule) -> None:
        self._rules[rule.rule_id] = rule

    def register_defaults(self) -> None:
        self.register(SecretsRule())
        self.register(DynamicExecutionRule())
        self.register(SubprocessRule())
        self.register(SQLInjectionRule())
        self.register(PathTraversalRule())
        self.register(DeserializationRule())
        self.register(PermissiveCORSRule())
        self.register(WeakCryptographyRule())
        self.register(InsecureCookieRule())
        self.register(MissingAuthCheckRule())

    def get_rule(self, rule_id: str) -> Optional[BaseSecurityRule]:
        return self._rules.get(rule_id)

    @property
    def all_rules(self) -> List[BaseSecurityRule]:
        return list(self._rules.values())

    def scan_file(
        self,
        code_text: str,
        file_path: str,
        language: str,
        context: Optional[ExtractedFileContext] = None,
    ) -> List[RawSecurityFinding]:
        findings: List[RawSecurityFinding] = []
        for rule in self._rules.values():
            try:
                rule_findings = rule.analyze_file(code_text, file_path, language, context=context)
                findings.extend(rule_findings)
            except Exception:
                continue
        return findings

security_registry = SecurityRuleRegistry()
