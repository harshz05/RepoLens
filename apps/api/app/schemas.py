from datetime import datetime
from typing import Optional, List
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
