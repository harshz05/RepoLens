import os
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, List, Any
from sqlalchemy import (
    String, Text, Integer, Float, Boolean, DateTime, ForeignKey, UniqueConstraint, Index, Numeric
)
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

try:
    from pgvector.sqlalchemy import Vector as PGVector
except ImportError:
    PGVector = None

class Base(DeclarativeBase):
    pass

def generate_uuid_str() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class VectorType(TypeDecorator):
    """
    Dialect-agnostic vector type.
    In PostgreSQL: maps to pgvector.sqlalchemy.Vector(dim).
    In SQLite: maps to Text (storing JSON serialized list of floats) with automatic conversion.
    """
    impl = Text
    cache_ok = True

    def __init__(self, dim: int = 768, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and PGVector is not None:
            return dialect.type_descriptor(PGVector(self.dim))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            if dialect.name == "postgresql" and PGVector is not None:
                return value
            return json.dumps(list(value))
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                cleaned = value.strip("[]")
                if cleaned:
                    return [float(x) for x in cleaned.split(",") if x.strip()]
                return []
        if isinstance(value, (list, tuple)):
            return list(value)
        return value

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    github_user_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    repositories: Mapped[List["Repository"]] = relationship("Repository", back_populates="user", cascade="all, delete-orphan")

class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("owner", "name", name="uq_repo_owner_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    github_url: Mapped[str] = mapped_column(String(512), nullable=False)
    owner: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(100), default="main", nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="repositories")
    versions: Mapped[List["RepositoryVersion"]] = relationship("RepositoryVersion", back_populates="repository", cascade="all, delete-orphan")
    chat_sessions: Mapped[List["ChatSession"]] = relationship("ChatSession", back_populates="repository", cascade="all, delete-orphan")

class RepositoryVersion(Base):
    __tablename__ = "repository_versions"
    __table_args__ = (
        UniqueConstraint("repository_id", "commit_hash", name="uq_repo_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    repository_id: Mapped[str] = mapped_column(String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    commit_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    branch: Mapped[str] = mapped_column(String(100), nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)  # PENDING, IN_PROGRESS, COMPLETED, FAILED
    embedding_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    embedding_dimension: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    repository: Mapped["Repository"] = relationship("Repository", back_populates="versions")
    analysis_runs: Mapped[List["AnalysisRun"]] = relationship("AnalysisRun", back_populates="repository_version", cascade="all, delete-orphan")
    audit_runs: Mapped[List["AuditRun"]] = relationship("AuditRun", back_populates="repository_version", cascade="all, delete-orphan")
    files: Mapped[List["File"]] = relationship("File", back_populates="repository_version", cascade="all, delete-orphan")

class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    repository_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("repository_versions.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="QUEUED", nullable=False)
    current_step: Mapped[str] = mapped_column(String(100), default="QUEUED", nullable=False)
    progress_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    step_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    repository_version: Mapped["RepositoryVersion"] = relationship("RepositoryVersion", back_populates="analysis_runs")

class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("repository_version_id", "path", name="uq_repo_file_path"),
        Index("idx_files_repo_ver", "repository_version_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    repository_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("repository_versions.id", ondelete="CASCADE"), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    repository_version: Mapped["RepositoryVersion"] = relationship("RepositoryVersion", back_populates="files")
    symbols: Mapped[List["Symbol"]] = relationship("Symbol", back_populates="file", cascade="all, delete-orphan")
    code_chunks: Mapped[List["CodeChunk"]] = relationship("CodeChunk", back_populates="file", cascade="all, delete-orphan")

class Symbol(Base):
    __tablename__ = "symbols"
    __table_args__ = (
        Index("idx_symbols_file", "file_id"),
        Index("idx_symbols_kind", "kind"),
        Index("idx_symbols_fqn", "fully_qualified_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fully_qualified_name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)  # function, class, method, variable, api_endpoint, db_model
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    start_col: Mapped[int] = mapped_column(Integer, nullable=False)
    end_col: Mapped[int] = mapped_column(Integer, nullable=False)
    signature: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    docstring: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    file: Mapped["File"] = relationship("File", back_populates="symbols")
    caller_dependencies: Mapped[List["Dependency"]] = relationship("Dependency", foreign_keys="[Dependency.caller_symbol_id]", back_populates="caller_symbol", cascade="all, delete-orphan")
    callee_dependencies: Mapped[List["Dependency"]] = relationship("Dependency", foreign_keys="[Dependency.callee_symbol_id]", back_populates="callee_symbol", cascade="all, delete-orphan")

class Dependency(Base):
    __tablename__ = "dependencies"
    __table_args__ = (
        Index("idx_deps_caller", "caller_symbol_id"),
        Index("idx_deps_callee", "callee_symbol_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    caller_symbol_id: Mapped[str] = mapped_column(String(36), ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False)
    callee_symbol_id: Mapped[str] = mapped_column(String(36), ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False)
    dependency_type: Mapped[str] = mapped_column(String(50), nullable=False)  # call, inheritance, import, instantiates, references
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)

    caller_symbol: Mapped["Symbol"] = relationship("Symbol", foreign_keys=[caller_symbol_id], back_populates="caller_dependencies")
    callee_symbol: Mapped["Symbol"] = relationship("Symbol", foreign_keys=[callee_symbol_id], back_populates="callee_dependencies")

class CodeChunk(Base):
    __tablename__ = "code_chunks"
    __table_args__ = (
        Index("idx_chunks_file", "file_id"),
        Index("idx_chunks_symbol", "symbol_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    symbol_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("symbols.id", ondelete="SET NULL"), nullable=True)
    symbol_fqn: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    embedding_dimension: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    embedding: Mapped[Optional[List[float]]] = mapped_column(VectorType(dim=768), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    file: Mapped["File"] = relationship("File", back_populates="code_chunks")
    symbol: Mapped[Optional["Symbol"]] = relationship("Symbol", lazy="selectin")

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("idx_chat_sessions_repo", "repository_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    repository_id: Mapped[str] = mapped_column(String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="New Architectural Chat", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    repository: Mapped["Repository"] = relationship("Repository", back_populates="chat_sessions")
    messages: Mapped[List["ChatMessage"]] = relationship("ChatMessage", back_populates="chat_session", cascade="all, delete-orphan", lazy="selectin")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("idx_chat_messages_session", "chat_session_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    chat_session_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_context_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    chat_session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")
    citations: Mapped[List["Citation"]] = relationship("Citation", back_populates="message", cascade="all, delete-orphan", lazy="selectin")

class Citation(Base):
    __tablename__ = "citations"
    __table_args__ = (
        Index("idx_citations_message", "message_id"),
        Index("idx_citations_file", "file_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    message_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    symbol_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("symbols.id", ondelete="SET NULL"), nullable=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    text_snippet: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    message: Mapped["ChatMessage"] = relationship("ChatMessage", back_populates="citations")
 
# --- Milestone 4: Security & Code Quality Intelligence Models ---

class AuditRun(Base):
    __tablename__ = "audit_runs"
    __table_args__ = (
        Index("idx_audit_runs_version", "repository_version_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    repository_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("repository_versions.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="QUEUED", nullable=False)  # QUEUED, IN_PROGRESS, COMPLETED, FAILED
    current_step: Mapped[str] = mapped_column(String(100), default="QUEUED", nullable=False)
    progress_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    step_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Bounded 5-Dimension Health Metrics (0.0 - 100.0)
    health_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    security_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    maintainability_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    complexity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    coupling_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    architecture_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    summary_metrics_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    repository_version: Mapped["RepositoryVersion"] = relationship("RepositoryVersion", back_populates="audit_runs")
    security_findings: Mapped[List["SecurityFinding"]] = relationship("SecurityFinding", back_populates="audit_run", cascade="all, delete-orphan", lazy="selectin")
    quality_findings: Mapped[List["QualityFinding"]] = relationship("QualityFinding", back_populates="audit_run", cascade="all, delete-orphan", lazy="selectin")

class SecurityFinding(Base):
    __tablename__ = "security_findings"
    __table_args__ = (
        Index("idx_sec_findings_run", "audit_run_id"),
        Index("idx_sec_findings_severity", "severity"),
        Index("idx_sec_findings_category", "category"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    audit_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    symbol_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("symbols.id", ondelete="SET NULL"), nullable=True)
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    confidence: Mapped[float] = mapped_column(Float, nullable=False)   # 0.0 to 1.0
    detection_source: Mapped[str] = mapped_column(String(50), nullable=False)  # STATIC_RULE, AST_ANALYSIS, GRAPH_ANALYSIS, AI_ANALYSIS
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)  # Redacted snippet / AST trace
    remediation: Mapped[str] = mapped_column(Text, nullable=False)
    graph_reachability_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_ai_assisted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    audit_run: Mapped["AuditRun"] = relationship("AuditRun", back_populates="security_findings")
    file: Mapped["File"] = relationship("File", lazy="selectin")
    symbol: Mapped[Optional["Symbol"]] = relationship("Symbol", lazy="selectin")

class QualityFinding(Base):
    __tablename__ = "quality_findings"
    __table_args__ = (
        Index("idx_qual_findings_run", "audit_run_id"),
        Index("idx_qual_findings_metric", "metric_name"),
        Index("idx_qual_findings_severity", "severity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    audit_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    symbol_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("symbols.id", ondelete="SET NULL"), nullable=True)
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    detection_source: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    is_ai_assisted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    audit_run: Mapped["AuditRun"] = relationship("AuditRun", back_populates="quality_findings")
    file: Mapped["File"] = relationship("File", lazy="selectin")
    symbol: Mapped[Optional["Symbol"]] = relationship("Symbol", lazy="selectin")

