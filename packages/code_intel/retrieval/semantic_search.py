import math
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from packages.db.models import RepositoryVersion, File, Symbol, CodeChunk
from packages.code_intel.models import RankedChunk, EmbeddingVersionMismatchError
from packages.code_intel.embeddings.provider import BaseEmbeddingProvider, get_embedding_provider

def compute_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not vec_a or not vec_b:
        return 0.0
    dim = min(len(vec_a), len(vec_b))
    if dim == 0:
        return 0.0

    dot = sum(vec_a[i] * vec_b[i] for i in range(dim))
    norm_a = math.sqrt(sum(vec_a[i] * vec_a[i] for i in range(dim)))
    norm_b = math.sqrt(sum(vec_b[i] * vec_b[i] for i in range(dim)))

    if norm_a < 1e-12 or norm_b < 1e-12:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))

class SemanticSearcher:
    """
    Dense Vector Semantic Searcher.
    Executes cosine similarity search over code chunks with model version compatibility checks.
    """

    @classmethod
    async def search(
        cls,
        session: AsyncSession,
        repository_version_id: str,
        query: str,
        provider: Optional[BaseEmbeddingProvider] = None,
        limit: int = 10,
        file_filter: Optional[str] = None,
        language_filter: Optional[str] = None,
        kind_filter: Optional[str] = None,
    ) -> List[RankedChunk]:
        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        active_provider = provider or get_embedding_provider()

        # 1. Fetch RepositoryVersion to verify embedding model and dimension compatibility
        ver_stmt = select(RepositoryVersion).where(RepositoryVersion.id == repository_version_id)
        ver_res = await session.execute(ver_stmt)
        repo_ver = ver_res.scalar_one_or_none()

        if repo_ver and repo_ver.embedding_model:
            if (
                repo_ver.embedding_model != active_provider.model_name
                or (repo_ver.embedding_dimension and repo_ver.embedding_dimension != active_provider.dimension)
            ):
                raise EmbeddingVersionMismatchError(
                    f"Repository embeddings were indexed with {repo_ver.embedding_model} (dim {repo_ver.embedding_dimension}), "
                    f"which does not match active configuration {active_provider.model_name} (dim {active_provider.dimension}). Re-indexing required.",
                    stored_model=repo_ver.embedding_model,
                    stored_dim=repo_ver.embedding_dimension,
                    current_model=active_provider.model_name,
                    current_dim=active_provider.dimension,
                )

        # 2. Generate Query Vector Embedding with standardized task formatting
        query_vec = active_provider.embed_query(cleaned_query)

        # 3. Fetch candidate files
        file_stmt = select(File).where(File.repository_version_id == repository_version_id)
        if file_filter:
            file_stmt = file_stmt.where(File.path == file_filter)
        if language_filter:
            file_stmt = file_stmt.where(File.language == language_filter)

        file_res = await session.execute(file_stmt)
        files = file_res.scalars().all()
        file_map = {f.id: f for f in files}
        file_ids = list(file_map.keys())

        if not file_ids:
            return []

        # 4. Query code chunks
        chunk_stmt = select(CodeChunk).where(CodeChunk.file_id.in_(file_ids))
        chunk_res = await session.execute(chunk_stmt)
        all_chunks = chunk_res.scalars().all()

        if not all_chunks:
            return []

        # 5. Fetch all symbol kinds for chunks
        sym_ids = [c.symbol_id for c in all_chunks if c.symbol_id]
        sym_kind_map = {}
        if sym_ids:
            sym_stmt = select(Symbol.id, Symbol.kind).where(Symbol.id.in_(sym_ids))
            sym_res = await session.execute(sym_stmt)
            for s_id, s_kind in sym_res.all():
                sym_kind_map[s_id] = s_kind

        # 6. Compute similarities
        scored_chunks: List[tuple[CodeChunk, float]] = []
        for chunk in all_chunks:
            if kind_filter and chunk.symbol_id and sym_kind_map.get(chunk.symbol_id) != kind_filter:
                continue

            chunk_vec = chunk.embedding
            if chunk_vec:
                score = compute_cosine_similarity(query_vec, chunk_vec)
                scored_chunks.append((chunk, score))

        # Sort by similarity descending
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        top_chunks = scored_chunks[:limit]

        # 7. Build RankedChunk results
        results: List[RankedChunk] = []
        for chunk, score in top_chunks:
            file_obj = file_map.get(chunk.file_id)
            f_path = file_obj.path if file_obj else ""
            lang = file_obj.language if file_obj else chunk.language

            results.append(
                RankedChunk(
                    chunk_id=chunk.id,
                    file_id=chunk.file_id,
                    file_path=f_path,
                    language=lang,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    content=chunk.content,
                    score=round(score, 4),
                    match_type="semantic",
                    symbol_id=chunk.symbol_id,
                    symbol_fqn=chunk.symbol_fqn,
                    symbol_kind=sym_kind_map.get(chunk.symbol_id) if chunk.symbol_id else None,
                    embedding_model=chunk.embedding_model,
                )
            )

        return results
