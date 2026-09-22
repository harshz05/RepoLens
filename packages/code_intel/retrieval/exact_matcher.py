from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from packages.db.models import File, Symbol, CodeChunk
from packages.code_intel.models import RankedChunk

class ExactMatcher:
    """
    Direct AST Symbol and File Path Exact Matcher.
    Resolves queries targeting exact function names, class names, FQNs, or file paths.
    """

    @classmethod
    async def match(
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

        # 1. Look for matching files
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

        # 2. Look for exact matching symbols (name or FQN)
        sym_stmt = (
            select(Symbol)
            .where(
                Symbol.file_id.in_(file_ids),
                or_(
                    Symbol.name == cleaned_query,
                    Symbol.name.ilike(f"%{cleaned_query}%"),
                    Symbol.fully_qualified_name == cleaned_query,
                    Symbol.fully_qualified_name.endswith(f".{cleaned_query}"),
                )
            )
        )
        if kind_filter:
            sym_stmt = sym_stmt.where(Symbol.kind == kind_filter)

        sym_res = await session.execute(sym_stmt)
        matched_symbols = sym_res.scalars().all()

        results: List[RankedChunk] = []
        seen_chunk_ids = set()

        for sym in matched_symbols:
            # Find chunk for this symbol
            chunk_stmt = (
                select(CodeChunk)
                .where(CodeChunk.symbol_id == sym.id)
            )
            chunk_res = await session.execute(chunk_stmt)
            chunks = chunk_res.scalars().all()

            file_obj = file_map.get(sym.file_id)
            f_path = file_obj.path if file_obj else ""
            lang = file_obj.language if file_obj else ""

            for chunk in chunks:
                if chunk.id not in seen_chunk_ids:
                    seen_chunk_ids.add(chunk.id)
                    score = 1.0 if sym.name == cleaned_query or sym.fully_qualified_name == cleaned_query else 0.85
                    results.append(
                        RankedChunk(
                            chunk_id=chunk.id,
                            file_id=chunk.file_id,
                            file_path=f_path,
                            language=lang,
                            start_line=chunk.start_line,
                            end_line=chunk.end_line,
                            content=chunk.content,
                            score=score,
                            match_type="exact",
                            symbol_id=sym.id,
                            symbol_fqn=sym.fully_qualified_name,
                            symbol_kind=sym.kind,
                            embedding_model=chunk.embedding_model,
                        )
                    )

        # 3. Check for exact file path match
        path_matched_files = [f for f in files if f.path == cleaned_query or f.path.endswith(f"/{cleaned_query}")]
        for p_file in path_matched_files:
            chunk_stmt = select(CodeChunk).where(CodeChunk.file_id == p_file.id).order_by(CodeChunk.start_line).limit(3)
            chunk_res = await session.execute(chunk_stmt)
            for chunk in chunk_res.scalars().all():
                if chunk.id not in seen_chunk_ids:
                    seen_chunk_ids.add(chunk.id)
                    results.append(
                        RankedChunk(
                            chunk_id=chunk.id,
                            file_id=p_file.id,
                            file_path=p_file.path,
                            language=p_file.language,
                            start_line=chunk.start_line,
                            end_line=chunk.end_line,
                            content=chunk.content,
                            score=0.9,
                            match_type="exact",
                            symbol_id=chunk.symbol_id,
                            symbol_fqn=chunk.symbol_fqn,
                            symbol_kind="file_match",
                            embedding_model=chunk.embedding_model,
                        )
                    )

        return results[:limit]
