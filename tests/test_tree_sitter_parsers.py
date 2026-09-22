import pytest
from packages.code_intel.parsers.python_parser import PythonTreeSitterParser
from packages.code_intel.parsers.typescript_parser import TypeScriptTreeSitterParser
from packages.code_intel.parsers.registry import parser_registry

def test_python_tree_sitter_parser_symbols_and_routes():
    code = b"""
from fastapi import FastAPI, Depends

app = FastAPI()

class DatabaseModel(Base):
    '''Database entity model.'''
    def __init__(self, table_name: str):
        self.table_name = table_name

    def get_table_name(self) -> str:
        '''Return table name.'''
        return self.table_name

@app.get('/api/v1/health')
async def health_check() -> dict:
    '''Health check gateway route.'''
    return {'status': 'healthy'}
"""
    parser = PythonTreeSitterParser()
    ctx = parser.parse(code, "apps/api/app/main.py")

    assert ctx.language == "python"
    assert len(ctx.symbols) >= 4

    sym_dict = {s.name: s for s in ctx.symbols}
    assert "DatabaseModel" in sym_dict
    assert sym_dict["DatabaseModel"].kind == "db_model"
    assert sym_dict["DatabaseModel"].docstring == "Database entity model."
    assert "class DatabaseModel(Base)" in sym_dict["DatabaseModel"].signature

    assert "health_check" in sym_dict
    assert sym_dict["health_check"].kind == "api_endpoint"
    assert sym_dict["health_check"].docstring == "Health check gateway route."
    assert "async def health_check()" in sym_dict["health_check"].signature

    assert "get_table_name" in sym_dict
    assert sym_dict["get_table_name"].kind == "method"

def test_typescript_tree_sitter_parser_components_hooks_interfaces():
    code = b"""
import React, { useState, useEffect } from 'react';

export interface UserProps {
    id: string;
    username: string;
}

export function useUserData(userId: string) {
    const [user, setUser] = useState<UserProps | null>(null);
    useEffect(() => {
        console.log('Fetching user', userId);
    }, [userId]);
    return user;
}

export const UserCard = ({ id, username }: UserProps) => {
    const data = useUserData(id);
    return (
        <div className="user-card">
            <h3>{username}</h3>
        </div>
    );
};

export class AuthService extends BaseService {
    async login() {
        return true;
    }
}
"""
    parser = TypeScriptTreeSitterParser(mode="tsx")
    ctx = parser.parse(code, "apps/web/components/UserCard.tsx")

    assert ctx.language == "typescript"
    sym_dict = {s.name: s for s in ctx.symbols}

    assert "UserProps" in sym_dict
    assert sym_dict["UserProps"].kind == "interface"

    assert "useUserData" in sym_dict
    assert sym_dict["useUserData"].kind == "hook"

    assert "UserCard" in sym_dict
    assert sym_dict["UserCard"].kind == "component"

    assert "AuthService" in sym_dict
    assert sym_dict["AuthService"].kind == "class"
    assert "extends BaseService" in sym_dict["AuthService"].signature

def test_parser_registry_extension_mapping():
    assert parser_registry.get_parser_for_path("server.py") is not None
    assert parser_registry.get_parser_for_path("server.py").language_name == "python"

    assert parser_registry.get_parser_for_path("Component.tsx") is not None
    assert parser_registry.get_parser_for_path("Component.tsx").language_name == "typescript"

    assert parser_registry.get_parser_for_path("script.js") is not None
    assert parser_registry.get_parser_for_path("script.js").language_name == "javascript"
