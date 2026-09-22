import pytest
from packages.code_intel.parsers.python_parser import PythonTreeSitterParser
from packages.code_intel.parsers.typescript_parser import TypeScriptTreeSitterParser
from packages.code_intel.graph.builder import DependencyGraphBuilder

def test_python_call_and_inheritance_extraction():
    code_service = b"""
class BaseService:
    def execute(self):
        pass

class UserService(BaseService):
    def get_user(self, user_id):
        self.validate(user_id)
        return self.fetch_from_db(user_id)

    def validate(self, user_id):
        pass

    def fetch_from_db(self, user_id):
        pass
"""
    parser = PythonTreeSitterParser()
    ctx = parser.parse(code_service, "services/user_service.py")

    builder = DependencyGraphBuilder([ctx])
    deps = builder.resolve_dependencies()

    # Check inheritance
    inh_deps = [d for d in deps if d.dependency_type == "inheritance"]
    assert len(inh_deps) >= 1
    assert inh_deps[0].caller_fqn == "services/user_service.py::UserService"
    assert inh_deps[0].callee_fqn == "services/user_service.py::BaseService"

    # Check intra-class method calls
    method_calls = [d for d in deps if d.dependency_type == "method_call"]
    callee_names = [d.callee_fqn.split("::")[-1] for d in method_calls]
    assert any("UserService.validate" in c for c in callee_names)
    assert any("UserService.fetch_from_db" in c for c in callee_names)

def test_cross_file_import_resolution():
    code_utils = b"""
def hash_password(password: str) -> str:
    return 'hashed_' + password
"""
    code_auth = b"""
from utils.crypto import hash_password

def register_user(raw_pwd: str):
    hashed = hash_password(raw_pwd)
    return hashed
"""
    parser = PythonTreeSitterParser()
    ctx_utils = parser.parse(code_utils, "utils/crypto.py")
    ctx_auth = parser.parse(code_auth, "services/auth.py")

    builder = DependencyGraphBuilder([ctx_utils, ctx_auth])
    deps = builder.resolve_dependencies()

    auth_to_crypto = [
        d for d in deps
        if d.caller_fqn == "services/auth.py::register_user" and d.callee_fqn == "utils/crypto.py::hash_password"
    ]
    assert len(auth_to_crypto) == 1
    assert auth_to_crypto[0].dependency_type in ("call", "instantiates")
