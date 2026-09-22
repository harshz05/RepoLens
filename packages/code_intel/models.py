from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class ExtractedSymbol:
    name: str
    fully_qualified_name: str
    kind: str  # 'function', 'class', 'method', 'api_endpoint', 'db_model', 'interface', 'component', 'hook'
    start_line: int
    end_line: int
    start_col: int
    end_col: int
    signature: Optional[str] = None
    docstring: Optional[str] = None
    file_path: Optional[str] = None
    parent_fqn: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RawCallReference:
    caller_fqn: Optional[str]
    callee_name: str
    callee_module: Optional[str]
    line_number: int
    col_offset: int
    call_type: str  # 'call', 'method_call', 'inheritance', 'instantiates', 'references'
    file_path: str
    arguments: List[str] = field(default_factory=list)

@dataclass
class RawImportReference:
    module_name: str
    imported_symbol: Optional[str]  # None if 'import foo' or '*'
    alias: Optional[str]
    is_relative: bool
    file_path: str
    line_number: int

@dataclass
class ExtractedFileContext:
    file_path: str
    language: str
    symbols: List[ExtractedSymbol] = field(default_factory=list)
    calls: List[RawCallReference] = field(default_factory=list)
    imports: List[RawImportReference] = field(default_factory=list)
    framework_metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ResolvedDependency:
    caller_symbol_id: Optional[str]
    callee_symbol_id: Optional[str]
    caller_fqn: str
    callee_fqn: str
    dependency_type: str  # 'call', 'method_call', 'inheritance', 'import', 'instantiates', 'references'
    file_id: Optional[str]
    file_path: str
    line_number: int
    confidence: float = 1.0

# --- Milestone 3: Chunking & Retrieval Models ---

@dataclass
class ExtractedChunk:
    file_path: str
    start_line: int
    end_line: int
    content: str
    token_count: int
    language: str
    metadata_title: str
    symbol_id: Optional[str] = None
    symbol_fqn: Optional[str] = None
    symbol_kind: Optional[str] = None
    embedding: Optional[List[float]] = None

@dataclass
class GraphContextSummary:
    symbol_fqn: str
    kind: str
    callers: List[str] = field(default_factory=list)  # caller symbol FQNs / signatures
    callees: List[str] = field(default_factory=list)  # callee symbol FQNs / signatures
    parent_scope: Optional[str] = None
    file_path: Optional[str] = None

@dataclass
class RankedChunk:
    chunk_id: str
    file_id: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    content: str
    score: float
    match_type: str  # 'exact', 'semantic', 'keyword', 'hybrid'
    symbol_id: Optional[str] = None
    symbol_fqn: Optional[str] = None
    symbol_kind: Optional[str] = None
    graph_context: Optional[GraphContextSummary] = None
    embedding_model: Optional[str] = None

@dataclass
class RetrievalResult:
    query: str
    total_results: int
    chunks: List[RankedChunk] = field(default_factory=list)

@dataclass
class CitationRecord:
    file_path: str
    start_line: int
    end_line: int
    snippet: str
    confidence_score: float
    symbol_name: Optional[str] = None
    file_id: Optional[str] = None
    symbol_id: Optional[str] = None

class EmbeddingVersionMismatchError(Exception):
    """Raised when repository version embedding model or dimension does not match active application configuration."""
    def __init__(self, message: str, stored_model: Optional[str] = None, stored_dim: Optional[int] = None, current_model: str = "", current_dim: int = 0):
        super().__init__(message)
        self.stored_model = stored_model
        self.stored_dim = stored_dim
        self.current_model = current_model
        self.current_dim = current_dim

