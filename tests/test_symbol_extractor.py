import pytest
from packages.code_intel.symbol_extractor import extract_file_symbols

def test_extract_python_symbols():
    code = """
import os

class User(Base):
    '''User database model.'''
    def __init__(self, name: str):
        self.name = name

@app.get('/api/users')
async def get_users():
    '''Fetch users.'''
    return []
"""
    symbols = extract_file_symbols(code, "app/main.py", "python")
    symbol_names = [s.name for s in symbols]

    assert "User" in symbol_names
    assert "__init__" in symbol_names
    assert "get_users" in symbol_names

    get_users_sym = next(s for s in symbols if s.name == "get_users")
    assert get_users_sym.kind == "api_endpoint"
    assert get_users_sym.docstring == "Fetch users."

def test_extract_typescript_symbols():
    code = """
export interface UserProfile {
    id: string;
    name: string;
}

export class AuthService {
    async login() {}
}

export const fetchProfile = (id: string) => {
    return {};
};
"""
    symbols = extract_file_symbols(code, "src/auth.ts", "typescript")
    symbol_names = [s.name for s in symbols]

    assert "UserProfile" in symbol_names
    assert "AuthService" in symbol_names
    assert "fetchProfile" in symbol_names
