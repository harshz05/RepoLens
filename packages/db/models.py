import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    String, Text, Integer, Float, Boolean, DateTime, ForeignKey, UniqueConstraint, Index, Numeric
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

class Base(DeclarativeBase):
    pass

def generate_uuid_str() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

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

    repository: Mapped["Repository"] = relationship("Repository", back_populates="versions")
    analysis_runs: Mapped[List["AnalysisRun"]] = relationship("AnalysisRun", back_populates="repository_version", cascade="all, delete-orphan")
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
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    symbol_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("symbols.id", ondelete="SET NULL"), nullable=True)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    file: Mapped["File"] = relationship("File", back_populates="code_chunks")
