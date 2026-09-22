import re
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from packages.db.models import File, Symbol, CodeChunk
from packages.code_intel.models import RankedChunk

class KeywordSearcher:
    """
    Trigram and Keyword Searcher.
    Matches queries against code chunk content, symbol docstrings, and signatures.
    """

    @classmethod
    async def search(
        cls,
        session: AsyncSession,
        repository_version_id: str,
        query: str,
        limit: int = 10,
        file_filter: Optional[str] = None,
        language_filter: Optional[str] = None,
        kind_filter: Optional[str] = None,
    ) -> List[RankedChunk]:
        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        tokens = [t.lower() for t in re.findall(r"\w+", cleaned_query) if len(t) > 2]
        if not tokens:
            tokens = [cleaned_query.lower()]

        # Fetch files
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

        # Build conditions for tokens
        clauses = []
        for t in tokens[:5]:
            clauses.append(CodeChunk.content.ilike(f"%{t}%"))
            clauses.append(CodeChunk.symbol_fqn.ilike(f"%{t}%"))

        chunk_stmt = (
            select(CodeChunk)
            .where(
                CodeChunk.file_id.in_(file_ids),
                or_(*clauses)
            )
        )
        chunk_res = await session.execute(chunk_stmt)
        matched_chunks = chunk_res.scalars().all()

        scored_chunks: List[tuple[CodeChunk, float]] = []
        query_lower = cleaned_query.lower()

        for chunk in matched_chunks:
            content_lower = chunk.content.lower()
            fqn_lower = (chunk.symbol_fqn or "").lower()

            # Calculate keyword match density
            token_hits = sum(1 for t in tokens if t in content_lower or t in fqn_lower)
            exact_phrase_bonus = 0.4 if query_lower in content_lower or query_lower in fqn_lower else 0.0
            score = min(1.0, (token_hits / max(len(tokens), 1)) * 0.6 + exact_phrase_bonus)

            scored_chunks.append((chunk, score))

        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        top_chunks = scored_chunks[:limit]

        # Fetch symbol kinds
        sym_ids = [c.symbol_id for c, _ in top_chunks if c.symbol_id]
        sym_kind_map = {}
        if sym_ids:
            sym_stmt = select(Symbol.id, Symbol.kind).where(Symbol.id.in_(sym_ids))
            sym_res = await session.execute(sym_stmt)
            for s_id, s_kind in sym_res.all():
                sym_kind_map[s_id] = s_kind

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
                    match_type="keyword",
                    symbol_id=chunk.symbol_id,
                    symbol_fqn=chunk.symbol_fqn,
                    symbol_kind=sym_kind_map.get(chunk.symbol_id) if chunk.symbol_id else None,
                    embedding_model=chunk.embedding_model,
                )
            )

        return results
