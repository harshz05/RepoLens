import re
from typing import List, Tuple

class SecretRedactor:
    """
    Masks and redacts sensitive credentials, tokens, and keys.
    Prevents raw secrets from being persisted in the database or exposed via API / UI.
    """

    KNOWN_PATTERNS: List[Tuple[str, re.Pattern]] = [
        ("AWS_KEY", re.compile(r"(AKIA[0-9A-Z]{16})")),
        ("GITHUB_TOKEN", re.compile(r"(ghp_[0-9a-zA-Z]{36}|github_pat_[0-9a-zA-Z_]{82})")),
        ("SLACK_TOKEN", re.compile(r"(xox[baprs]-[0-9a-zA-Z]{10,48})")),
        ("STRIPE_KEY", re.compile(r"(sk_live_[0-9a-zA-Z]{24})")),
        ("GENERIC_BEARER", re.compile(r"(Bearer\s+)([a-zA-Z0-9_\-\.]{20,})", re.IGNORECASE)),
        ("PRIVATE_KEY", re.compile(r"-----BEGIN[ A-Z0-9_-]+PRIVATE KEY-----.*?-----END[ A-Z0-9_-]+PRIVATE KEY-----", re.DOTALL)),
        ("PASSWORD_ASSIGN", re.compile(r"""((?:password|passwd|secret|api_key|apikey|auth_token)\s*[:=]\s*["'])([^"']{6,})(["'])""", re.IGNORECASE)),
    ]

    @classmethod
    def mask_secret(cls, secret: str) -> str:
        """Mask a single secret string, retaining minimal prefix and suffix for identification."""
        if not secret:
            return ""
        if len(secret) <= 8:
            return "*" * len(secret)
        prefix = secret[:4]
        suffix = secret[-2:]
        masked_middle = "*" * max(6, len(secret) - 6)
        return f"{prefix}{masked_middle}{suffix}"

    @classmethod
    def redact_text(cls, text: str) -> str:
        """Scans arbitrary text or code snippet and redacts all recognized sensitive substrings."""
        if not text:
            return ""
        redacted = text

        for name, pattern in cls.KNOWN_PATTERNS:
            if name == "GENERIC_BEARER":
                redacted = pattern.sub(lambda m: f"{m.group(1)}{cls.mask_secret(m.group(2))}", redacted)
            elif name == "PASSWORD_ASSIGN":
                redacted = pattern.sub(lambda m: f"{m.group(1)}{cls.mask_secret(m.group(2))}{m.group(3)}", redacted)
            elif name == "PRIVATE_KEY":
                redacted = pattern.sub("-----BEGIN PRIVATE KEY-----\n[REDACTED_PRIVATE_KEY]\n-----END PRIVATE KEY-----", redacted)
            else:
                redacted = pattern.sub(lambda m: cls.mask_secret(m.group(1)), redacted)

        return redacted
