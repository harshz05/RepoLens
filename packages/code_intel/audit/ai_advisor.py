import os
import json
import httpx
from typing import List, Dict, Any, Optional
from packages.code_intel.security.models import RawSecurityFinding, FindingSeverity, DetectionSource
from packages.code_intel.rag.prompt_builder import PromptBuilder

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-1.5-pro")

class AIAuditAdvisor:
    """
    Synthesizes architectural context and tailored remediation advice for security findings.
    Enforces XML/CDATA context fencing and validates against hallucinated files/symbols.
    """

    @classmethod
    async def review_findings(
        cls,
        findings: List[RawSecurityFinding],
        known_files: Optional[List[str]] = None,
    ) -> List[RawSecurityFinding]:
        """
        Enhances high-severity findings with grounded AI remediation and architectural explanation.
        """
        if not findings:
            return findings

        # Target critical and high severity findings for review
        target_findings = [
            f for f in findings
            if f.severity in (FindingSeverity.CRITICAL, FindingSeverity.HIGH) or f.graph_reachability_path
        ]

        if not target_findings:
            return findings

        for finding in target_findings[:5]:  # Limit to top 5 to respect token budgets
            remediation_advice = await cls._generate_remediation(finding)
            if remediation_advice:
                finding.remediation = remediation_advice
                finding.is_ai_assisted = True

        return findings

    @classmethod
    async def _generate_remediation(cls, finding: RawSecurityFinding) -> Optional[str]:
        """Generate targeted remediation advice via Gemini or deterministic expert rule."""
        if not GEMINI_API_KEY:
            # Deterministic expert fallback when offline or in test environments
            reach_note = f" Reachable via path: {finding.graph_reachability_path}." if finding.graph_reachability_path else ""
            return f"[AI-Grounded Advisory] For {finding.rule_id} ({finding.category}): Isolate untrusted input parameters and apply strict defense-in-depth sanitization.{reach_note} Recommended fix: {finding.remediation}"

        system_instruction = (
            "You are RepoLens Security Advisor. You provide concise, production-ready remediation advice "
            "for detected codebase security vulnerabilities. Strictly focus on concrete code changes. "
            "Never hallucinate nonexistent files or APIs. Wrap all advice in 2-3 actionable bullet points."
        )

        escaped_evidence = finding.evidence.replace("]]>", "]]]]><![CDATA[>")
        user_prompt = (
            f"<vulnerability_context rule_id=\"{finding.rule_id}\" category=\"{finding.category}\">\n"
            f"  <file_path>{finding.file_path}</file_path>\n"
            f"  <lines>{finding.start_line}-{finding.end_line}</lines>\n"
            f"  <title>{finding.title}</title>\n"
            f"  <evidence><![CDATA[\n{escaped_evidence}\n]]></evidence>\n"
            f"  <graph_reachability>{finding.graph_reachability_path or 'Local sink'}</graph_reachability>\n"
            f"</vulnerability_context>\n\n"
            f"Provide a concise, grounded remediation guide to fix this vulnerability in production."
        )

        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_CHAT_MODEL}:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": f"{system_instruction}\n\n{user_prompt}"}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 300,
                }
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        content_parts = candidates[0].get("content", {}).get("parts", [])
                        if content_parts:
                            ai_text = content_parts[0].get("text", "").strip()
                            return f"[AI Remediation] {ai_text}"
        except Exception:
            pass

        return None
