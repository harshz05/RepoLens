"""
Sprint 2 — security rule tests: per-rule positive/negative fixtures, multi-line detection,
central redaction, rule-error reporting, and honest detection-source labels.
"""
import logging
import pytest

from packages.code_intel.models import ExtractedFileContext, ExtractedSymbol, RawCallReference
from packages.code_intel.security.base_rule import BaseSecurityRule, iter_logical_lines
from packages.code_intel.security.models import DetectionSource, FindingSeverity
from packages.code_intel.security.registry import SecurityRuleRegistry, security_registry

# Built by concatenation so this test file doesn't itself contain a literal secret.
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
BEARER = "Bearer " + "abcdefghijklmnopqrstuvwxyz123456"


def run(rule_id: str, code: str, path: str = "app.py", language: str = "python", context=None):
    rule = security_registry.get_rule(rule_id)
    return rule.analyze_file(code, path, language, context=context)


# --------------------------------------------------------------- per-rule fixtures

POSITIVE = [
    ("SEC-001", f'KEY = "{AWS_KEY}"', "python"),
    ("SEC-002", "result = eval(user_input)", "python"),
    ("SEC-002", 'const f = new Function("return " + x);', "javascript"),
    ("SEC-003", 'subprocess.run(f"ls {d}", shell=True)', "python"),
    ("SEC-003", 'os.system("rm " + path)', "python"),
    ("SEC-003", "child_process.exec(cmd)", "javascript"),
    ("SEC-004", 'cursor.execute(f"SELECT * FROM t WHERE id = {uid}")', "python"),
    ("SEC-004", "db.query(`SELECT * FROM t WHERE id = ${id}`)", "javascript"),
    ("SEC-005", 'data = open(f"/srv/{name}").read()', "python"),
    ("SEC-005", "fs.readFile(path.join(base, req.query.f), cb)", "javascript"),
    ("SEC-006", "obj = pickle.loads(blob)", "python"),
    ("SEC-006", "cfg = yaml.load(stream)", "python"),
    ("SEC-007", 'app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)', "python"),
    ("SEC-008", "digest = hashlib.md5(data).hexdigest()", "python"),
    ("SEC-009", 'resp.set_cookie("sid", value, secure=False)', "python"),
    ("SEC-009", 'res.cookie("sid", value)', "javascript"),
]

NEGATIVE = [
    ("SEC-001", 'API_KEY = os.environ["API_KEY"]', "python"),
    ("SEC-001", 'password = "changeme"', "python"),
    ("SEC-002", "value = ast.literal_eval(text)", "python"),
    ("SEC-002", "# eval(user_input)", "python"),
    ("SEC-003", 'subprocess.run(["ls", d])', "python"),
    ("SEC-003", 'subprocess.run(["ls"], shell=False)', "python"),
    ("SEC-004", 'cursor.execute("SELECT * FROM t WHERE id = %s", (uid,))', "python"),
    ("SEC-005", 'data = open("config.json").read()', "python"),
    ("SEC-006", "cfg = yaml.load(stream, Loader=yaml.SafeLoader)", "python"),
    ("SEC-006", "cfg = yaml.safe_load(stream)", "python"),
    ("SEC-006", "data = json.loads(text)", "python"),
    ("SEC-007", 'app.add_middleware(CORSMiddleware, allow_origins=["https://app.example.com"], allow_credentials=True)', "python"),
    ("SEC-008", "digest = hashlib.md5(data, usedforsecurity=False)", "python"),
    ("SEC-008", "digest = hashlib.sha256(data)", "python"),
    ("SEC-009", 'resp.set_cookie("sid", value, secure=True, httponly=True)', "python"),
    ("SEC-009", 'res.cookie("sid", value, { httpOnly: true, secure: true })', "javascript"),
]


@pytest.mark.parametrize("rule_id, code, language", POSITIVE)
def test_rule_flags_vulnerable_code(rule_id, code, language):
    findings = run(rule_id, code, language=language)
    assert findings, f"{rule_id} should flag: {code}"
    assert all(f.rule_id == rule_id for f in findings)
    assert all(f.start_line == 1 for f in findings)


@pytest.mark.parametrize("rule_id, code, language", NEGATIVE)
def test_rule_ignores_safe_code(rule_id, code, language):
    assert run(rule_id, code, language=language) == []


# ------------------------------------------------------------ multi-line detection

def test_multiline_subprocess_call_is_detected_with_line_span():
    code = "x = 1\nsubprocess.run(\n    cmd,\n    shell=True,\n)\ny = 2\n"
    findings = run("SEC-003", code)
    assert len(findings) == 1
    assert (findings[0].start_line, findings[0].end_line) == (2, 5)


def test_multiline_sql_fstring_is_detected():
    code = 'cur.execute(\n    f"""\n    SELECT * FROM t\n    WHERE id = {uid}\n    """\n)\n'
    findings = run("SEC-004", code)
    assert len(findings) == 1 and findings[0].start_line == 1


def test_multiline_cookie_is_detected():
    code = 'resp.set_cookie(\n    "sid",\n    value,\n    httponly=False,\n)\n'
    assert len(run("SEC-009", code)) == 1


def test_logical_line_join_is_bounded():
    # An unbalanced bracket must never swallow the rest of the file.
    code = "x = foo(\n" + "\n".join(f"line{i}" for i in range(100))
    spans = list(iter_logical_lines(code, max_span=12))
    assert spans[0][1] - spans[0][0] <= 12
    assert len(spans) > 1


# --------------------------------------------------------------------- SEC-002 AST

def test_eval_ast_path_does_not_double_report():
    ctx = ExtractedFileContext(
        file_path="a.py", language="python",
        calls=[RawCallReference(caller_fqn=None, callee_name="eval", callee_module=None,
                                line_number=1, col_offset=0, call_type="call", file_path="a.py")],
    )
    findings = run("SEC-002", "eval(x)\n", path="a.py", context=ctx)
    assert len(findings) == 1
    assert findings[0].detection_source == DetectionSource.AST_ANALYSIS
    assert findings[0].severity == FindingSeverity.CRITICAL


# --------------------------------------------------------------------------- SEC-010

def _endpoint(name, route, signature, decorators):
    return ExtractedSymbol(
        name=name, fully_qualified_name=f"app.py::{name}", kind="api_endpoint",
        start_line=1, end_line=3, start_col=0, end_col=0, signature=signature, file_path="app.py",
        metadata={"route": route, "http_method": "DELETE", "decorators": decorators},
    )


def _ctx(sym):
    return ExtractedFileContext(file_path="app.py", language="python", symbols=[sym])


def test_sec010_flags_unprotected_admin_route():
    sym = _endpoint("purge", "/admin/purge", "def purge()", ['@app.delete("/admin/purge")'])
    assert len(run("SEC-010", "", context=_ctx(sym))) == 1


def test_sec010_function_name_does_not_count_as_auth_evidence():
    # Regression: "user" in the function NAME used to suppress the finding.
    sym = _endpoint("delete_all_users", "/admin/users", "def delete_all_users()", ['@app.delete("/admin/users")'])
    assert len(run("SEC-010", "", context=_ctx(sym))) == 1


def test_sec010_accepts_auth_dependency_in_params():
    sig = "def purge(user = Depends(get_current_user))"
    sym = _endpoint("purge", "/admin/purge", sig, ['@app.delete("/admin/purge")'])
    assert run("SEC-010", "", context=_ctx(sym)) == []


def test_sec010_accepts_auth_decorator():
    sym = _endpoint("purge", "/admin/purge", "def purge()", ['@app.delete("/admin/purge")', "@login_required"])
    assert run("SEC-010", "", context=_ctx(sym)) == []


def test_sec010_ignores_non_sensitive_routes():
    sym = _endpoint("list_items", "/items", "def list_items()", ['@app.get("/items")'])
    assert run("SEC-010", "", context=_ctx(sym)) == []


# ------------------------------------------------------ registry: redaction & errors

def test_registry_redacts_secrets_in_every_rules_evidence():
    # SEC-003 (not the secrets rule) would previously have stored the token verbatim.
    code = f'subprocess.run("curl -H \'Authorization: {BEARER}\'", shell=True)'
    findings = security_registry.scan_file(code, "deploy.py", "python")
    sub = [f for f in findings if f.rule_id == "SEC-003"]
    assert sub
    assert "abcdefghijklmnopqrstuvwxyz123456" not in sub[0].evidence


def test_registry_never_leaks_aws_key_in_secret_finding():
    findings = security_registry.scan_file(f'KEY = "{AWS_KEY}"', "cfg.py", "python")
    assert findings
    assert all(AWS_KEY not in f.evidence and AWS_KEY not in f.description for f in findings)


class _ExplodingRule(BaseSecurityRule):
    rule_id = "SEC-999"
    category = "Test"
    title = "Boom"
    default_severity = FindingSeverity.LOW
    detection_source = DetectionSource.STATIC_RULE

    def analyze_file(self, code_text, file_path, language, context=None):
        raise RuntimeError("boom")


def test_rule_failure_is_reported_not_silent(caplog):
    registry = SecurityRuleRegistry()
    registry.register(_ExplodingRule())
    errors = []
    with caplog.at_level(logging.ERROR):
        findings = registry.scan_file("result = eval(x)\n", "a.py", "python", errors=errors)

    assert any(f.rule_id == "SEC-002" for f in findings)  # other rules still ran
    assert errors == [{"rule_id": "SEC-999", "file_path": "a.py", "error": "RuntimeError('boom')"}]
    assert any("SEC-999" in rec.getMessage() for rec in caplog.records)


# ----------------------------------------------------------- honest detection labels

@pytest.mark.parametrize("rule_id", ["SEC-001", "SEC-003", "SEC-004", "SEC-005", "SEC-006", "SEC-007", "SEC-008", "SEC-009"])
def test_pattern_based_rules_are_labelled_static_rule(rule_id):
    assert security_registry.get_rule(rule_id).detection_source == DetectionSource.STATIC_RULE


def test_symbol_based_rule_is_labelled_ast_analysis():
    assert security_registry.get_rule("SEC-010").detection_source == DetectionSource.AST_ANALYSIS