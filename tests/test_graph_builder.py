import pytest
from packages.code_intel.parsers.python_parser import PythonTreeSitterParser
from packages.code_intel.parsers.typescript_parser import TypeScriptTreeSitterParser
from packages.code_intel.graph.builder import DependencyGraphBuilder

def test_graph_builder_payload_structure():
    code_py = b"""
def compute_hash(data: str):
    return '123'

def main():
    return compute_hash('test')
"""
    parser = PythonTreeSitterParser()
    ctx = parser.parse(code_py, "src/main.py")

    builder = DependencyGraphBuilder([ctx])
    payload = builder.build_graph_payload()

    assert payload["total_nodes"] == 2
    assert payload["total_edges"] == 1

    node_labels = [n["label"] for n in payload["nodes"]]
    assert "compute_hash" in node_labels
    assert "main" in node_labels

    edge = payload["edges"][0]
    assert edge["source"] == "src/main.py::main"
    assert edge["target"] == "src/main.py::compute_hash"
    assert edge["type"] in ("call", "method_call")
