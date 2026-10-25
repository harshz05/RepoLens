import logging
from typing import List, Dict, Optional
from packages.code_intel.models import ExtractedFileContext
from packages.code_intel.security.base_rule import BaseSecurityRule
from packages.code_intel.security.models import RawSecurityFinding
from packages.code_intel.security.redactor import SecretRedactor
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

logger = logging.getLogger(__name__)


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
        errors: Optional[List[dict]] = None,
    ) -> List[RawSecurityFinding]:
        """
        Run every rule on one file.

        - A failing rule never aborts the scan, but it is logged and (if `errors` is given)
          recorded, so a broken rule can't silently look like "no findings".
        - Redaction is applied centrally here, so no rule can leak a secret into the DB,
          the API, or an LLM prompt, regardless of which rule produced the evidence.
        """
        findings: List[RawSecurityFinding] = []
        for rule in self._rules.values():
            try:
                rule_findings = rule.analyze_file(code_text, file_path, language, context=context)
            except Exception as exc:  # noqa: BLE001 - isolation boundary for third-party-style rules
                logger.exception("Security rule %s failed on %s", rule.rule_id, file_path)
                if errors is not None:
                    errors.append({"rule_id": rule.rule_id, "file_path": file_path, "error": repr(exc)})
                continue

            for f in rule_findings:
                f.evidence = SecretRedactor.redact_text(f.evidence)
                f.description = SecretRedactor.redact_text(f.description)
            findings.extend(rule_findings)
        return findings


security_registry = SecurityRuleRegistry()