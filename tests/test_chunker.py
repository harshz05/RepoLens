import pytest
from packages.code_intel.chunking.chunker import ASTAwareChunker, estimate_tokens
from packages.code_intel.parsers.registry import parser_registry

def test_estimate_tokens():
    text = "def authenticate(username: str, token: str) -> bool:\n    return True"
    count = estimate_tokens(text)
    assert count > 0
    assert estimate_tokens("") == 0

def test_ast_aware_chunker_python():
    code = """import os
import sys

DEFAULT_TIMEOUT = 30

def helper_func(x: int) -> int:
    '''Simple helper.'''
    return x * 2

class UserService:
    '''User service business logic.'''
    def __init__(self, db_conn):
        self.db = db_conn

    def get_user(self, user_id: str):
        '''Fetch user by ID.'''
        return self.db.find(user_id)
"""
    file_path = "services/user_service.py"
    ctx = parser_registry.parse_file(code.encode("utf-8"), file_path)
    assert ctx is not None

    chunks = ASTAwareChunker.chunk_file(
        code_str=code,
        file_path=file_path,
        language="python",
        context=ctx,
    )

    assert len(chunks) >= 2

    # Check symbol chunks
    sym_chunks = [c for c in chunks if c.symbol_fqn is not None]
    assert len(sym_chunks) >= 2

    user_service_chunk = next((c for c in sym_chunks if "UserService" in (c.symbol_fqn or "")), None)
    assert user_service_chunk is not None
    assert "UserService" in user_service_chunk.content
    assert "title: services/user_service.py" in ASTAwareChunker.chunk_file(code, file_path, "python", ctx)[0].metadata_title or "services/user_service.py" in user_service_chunk.metadata_title

    # Check interstitial chunk
    interstitial_chunks = [c for c in chunks if c.symbol_kind == "module_scope"]
    assert len(interstitial_chunks) >= 1
    assert "import os" in interstitial_chunks[0].content or "DEFAULT_TIMEOUT" in interstitial_chunks[0].content

def test_ast_aware_chunker_sub_chunking():
    # Generate a massive function > 1000 tokens
    large_body = "\n".join([f"    x_{i} = calculate_value({i}) # processing line {i}" for i in range(300)])
    large_code = f"""def massive_computation():\n{large_body}\n    return True\n"""
    
    file_path = "utils/compute.py"
    ctx = parser_registry.parse_file(large_code.encode("utf-8"), file_path)

    chunks = ASTAwareChunker.chunk_file(
        code_str=large_code,
        file_path=file_path,
        language="python",
        context=ctx,
    )

    assert len(chunks) >= 2
    for c in chunks:
        assert c.token_count <= ASTAwareChunker.MAX_CHUNK_TOKENS + 100
