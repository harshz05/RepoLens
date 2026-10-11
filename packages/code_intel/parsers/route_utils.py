"""Helpers for extracting HTTP route information from decorator / call text."""
import re
from typing import Dict, Optional

_HTTP_METHODS = ("get", "post", "put", "delete", "patch", "head", "options")

# @router.post("/ingest", ...) / @app.get('/x') / @bp.get("/y")
_VERB_DECORATOR = re.compile(
    r"""@\s*[\w\.]+\.(get|post|put|delete|patch|head|options)\s*\(\s*(?:path\s*=\s*)?(?P<q>["'])(?P<route>.*?)(?P=q)""",
    re.IGNORECASE | re.DOTALL,
)
# @app.route("/x", methods=["POST", "GET"]) / @bp.route('/x')
_ROUTE_DECORATOR = re.compile(
    r"""@\s*[\w\.]+\.route\s*\(\s*(?:rule\s*=\s*)?(?P<q>["'])(?P<route>.*?)(?P=q)(?P<rest>.*)\)""",
    re.IGNORECASE | re.DOTALL,
)
_METHODS_KW = re.compile(r"""methods\s*=\s*[\[\(](?P<m>[^\]\)]*)[\]\)]""", re.IGNORECASE)


def extract_route_info(decorator: str) -> Optional[Dict[str, str]]:
    """
    Parse a decorator string and return {"route": ..., "http_method": ...} or None.
    Pure string analysis: never executes or imports repository code.
    """
    if not decorator:
        return None

    m = _VERB_DECORATOR.search(decorator)
    if m:
        return {"route": m.group("route"), "http_method": m.group(1).upper()}

    m = _ROUTE_DECORATOR.search(decorator)
    if m:
        methods = "GET"
        mm = _METHODS_KW.search(m.group("rest") or "")
        if mm:
            found = re.findall(r"""["']([A-Za-z]+)["']""", mm.group("m"))
            if found:
                methods = ",".join(x.upper() for x in found)
        return {"route": m.group("route"), "http_method": methods}

    return None