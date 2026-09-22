from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class IngestRepositoryRequest(BaseModel):
    github_url: str = Field(..., json_schema_extra={"example": "https://github.com/pallets/flask"})
    branch: str = Field(default="main", json_schema_extra={"example": "main"})

class IngestRepositoryResponse(BaseModel):
    repository_id: str
    repository_version_id: str
    analysis_run_id: str
    owner: str
    name: str
    status: str
    message: str

class SymbolSchema(BaseModel):
    id: str
    name: str
    fully_qualified_name: str
    kind: str
    start_line: int
    end_line: int
    signature: Optional[str] = None
    docstring: Optional[str] = None
    file_path: Optional[str] = None

class FileDetailSchema(BaseModel):
    id: str
    path: str
    language: str
    line_count: int
    byte_size: int
    symbol_count: int
    symbols: List[SymbolSchema] = []

class RepositorySummarySchema(BaseModel):
    id: str
    github_url: str
    owner: str
    name: str
    default_branch: str
    created_at: datetime
    latest_status: str
    total_files: int
    total_loc: int
    total_symbols: int
    total_dependencies: int = 0
    total_chunks: int = 0
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = None
    language_breakdown: dict

class AnalysisRunSchema(BaseModel):
    id: str
    status: str
    current_step: str
    progress_percentage: float
    step_details: Optional[str] = None
    error_log: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

# --- Milestone 2: Graph Schemas ---

class GraphNodeSchema(BaseModel):
    id: str
    label: str
    fqn: str
    kind: str
    file_path: str
    line_range: List[int]
    signature: Optional[str] = None
    docstring: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class GraphEdgeSchema(BaseModel):
    id: str
    source: str
    target: str
    type: str
    label: str
    line_number: int
    file_path: Optional[str] = None

class RepositoryGraphResponse(BaseModel):
    repository_id: str
    version_id: str
    total_nodes: int
    total_edges: int
    nodes: List[GraphNodeSchema]
    edges: List[GraphEdgeSchema]
    files_count: int
    languages: Dict[str, int]

class SymbolDependencyDetailResponse(BaseModel):
    symbol: SymbolSchema
    file_path: str
    callers: List[SymbolSchema]
    callees: List[SymbolSchema]
    incoming_edges: List[GraphEdgeSchema]
    outgoing_edges: List[GraphEdgeSchema]

# --- Milestone 3: Search & RAG Chat Schemas ---

class SearchRequest(BaseModel):
    query: str = Field(..., json_schema_extra={"example": "AuthService authenticate"})
    limit: int = Field(default=10, ge=1, le=50)
    mode: str = Field(default="hybrid", json_schema_extra={"example": "hybrid"})  # hybrid, semantic, exact
    language: Optional[str] = None
    file_path: Optional[str] = None
    kind: Optional[str] = None

class GraphContextSchema(BaseModel):
    symbol_fqn: str
    kind: str
    callers: List[str] = []
    callees: List[str] = []

class SearchResultItemSchema(BaseModel):
    chunk_id: str
    file_path: str
    symbol_fqn: Optional[str] = None
    kind: Optional[str] = None
    start_line: int
    end_line: int
    content: str
    score: float
    match_type: str
    graph_context: Optional[GraphContextSchema] = None
    embedding_model: Optional[str] = None

class SearchResponse(BaseModel):
    query: str
    total_results: int
    results: List[SearchResultItemSchema]

class ChatRequest(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "How is authentication handled in this repository?"})
    session_id: Optional[str] = None

class CitationSchema(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    symbol_name: Optional[str] = None
    snippet: str
    confidence_score: float

class ChatResponse(BaseModel):
    session_id: str
    message_id: str
    response: str
    citations: List[CitationSchema]
    retrieved_chunks: List[SearchResultItemSchema]

class ChatMessageSchema(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    citations: List[CitationSchema] = []

class ChatSessionSchema(BaseModel):
    id: str
    repository_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[ChatMessageSchema] = []

class ReindexResponse(BaseModel):
    repository_id: str
    version_id: str
    reindexed_chunks: int
    embedding_model: str
    embedding_dimension: int
    message: str

# --- Milestone 4: Security & Quality Audit Schemas ---

class AuditTriggerRequest(BaseModel):
    enable_ai_review: bool = Field(default=True)

class AuditRunResponse(BaseModel):
    audit_run_id: str
    repository_id: str
    version_id: str
    status: str
    message: str

class SecurityFindingSchema(BaseModel):
    id: str
    rule_id: str
    category: str
    severity: str
    confidence: float
    detection_source: str
    file_path: str
    start_line: int
    end_line: int
    title: str
    description: str
    evidence: str
    remediation: str
    symbol_name: Optional[str] = None
    graph_reachability_path: Optional[str] = None
    is_ai_assisted: bool = False
    created_at: datetime

class QualityFindingSchema(BaseModel):
    id: str
    rule_id: str
    metric_name: str
    title: str
    description: str
    severity: str
    confidence: float
    detection_source: str
    value: float
    threshold: float
    file_path: str
    start_line: int
    end_line: int
    recommendation: str
    symbol_name: Optional[str] = None
    is_ai_assisted: bool = False
    created_at: datetime

class AuditSummarySchema(BaseModel):
    id: str
    repository_id: str
    version_id: str
    status: str
    current_step: str
    progress_percentage: float
    step_details: Optional[str] = None
    error_log: Optional[str] = None
    health_score: Optional[float] = None
    security_score: Optional[float] = None
    maintainability_score: Optional[float] = None
    complexity_score: Optional[float] = None
    coupling_score: Optional[float] = None
    architecture_score: Optional[float] = None
    dimensions_summary: Dict[str, Any] = Field(default_factory=dict)
    total_security_findings: int = 0
    total_quality_findings: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


