from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from packages.code_intel.models import RankedChunk, RetrievalResult
from packages.code_intel.embeddings.provider import BaseEmbeddingProvider, get_embedding_provider
from packages.code_intel.retrieval.exact_matcher import ExactMatcher
from packages.code_intel.retrieval.semantic_search import SemanticSearcher
from packages.code_intel.retrieval.keyword_search import KeywordSearcher
from packages.code_intel.retrieval.context_expansion import ContextExpander

class HybridRetrievalEngine:
    """
    Multi-Signal Hybrid Code Retrieval Engine with Reciprocal Rank Fusion (RRF).
    Combines dense vector similarity, exact AST symbol identifiers, and keyword search.
    """

    RRF_K: int = 60
    WEIGHT_EXACT: float = 1.2
    WEIGHT_SEMANTIC: float = 1.0
    WEIGHT_KEYWORD: float = 0.8

    @classmethod
    async def retrieve(
        cls,
        session: AsyncSession,
        repository_version_id: str,
        query: str,
        mode: str = "hybrid",  # 'hybrid', 'semantic', 'exact'
        limit: int = 10,
        file_filter: Optional[str] = None,
        language_filter: Optional[str] = None,
        kind_filter: Optional[str] = None,
        provider: Optional[BaseEmbeddingProvider] = None,
        expand_graph_context: bool = True,
    ) -> RetrievalResult:
        cleaned_query = query.strip()
        if not cleaned_query:
            return RetrievalResult(query=query, total_results=0, chunks=[])

        active_provider = provider or get_embedding_provider()

        if mode == "exact":
            results = await ExactMatcher.match(
                session=session,
                repository_version_id=repository_version_id,
                query=cleaned_query,
                limit=limit,
                file_filter=file_filter,
                language_filter=language_filter,
                kind_filter=kind_filter,
            )
        elif mode == "semantic":
            results = await SemanticSearcher.search(
                session=session,
                repository_version_id=repository_version_id,
                query=cleaned_query,
                provider=active_provider,
                limit=limit,
                file_filter=file_filter,
                language_filter=language_filter,
                kind_filter=kind_filter,
            )
        else:
            # Hybrid Mode: Execute all 3 signals and fuse with RRF
            fetch_limit = max(limit * 2, 20)

            exact_list = await ExactMatcher.match(
                session=session,
                repository_version_id=repository_version_id,
                query=cleaned_query,
                limit=fetch_limit,
                file_filter=file_filter,
                language_filter=language_filter,
                kind_filter=kind_filter,
            )

            semantic_list = await SemanticSearcher.search(
                session=session,
                repository_version_id=repository_version_id,
                query=cleaned_query,
                provider=active_provider,
                limit=fetch_limit,
                file_filter=file_filter,
                language_filter=language_filter,
                kind_filter=kind_filter,
            )

            keyword_list = await KeywordSearcher.search(
                session=session,
                repository_version_id=repository_version_id,
                query=cleaned_query,
                limit=fetch_limit,
                file_filter=file_filter,
                language_filter=language_filter,
                kind_filter=kind_filter,
            )

            # Reciprocal Rank Fusion
            chunk_map: Dict[str, RankedChunk] = {}
            rrf_scores: Dict[str, float] = {}
            match_types: Dict[str, set] = {}

            def add_ranked_list(ranked_items: List[RankedChunk], weight: float, label: str):
                for rank, item in enumerate(ranked_items, start=1):
                    c_id = item.chunk_id
                    chunk_map[c_id] = item
                    match_types.setdefault(c_id, set()).add(label)
                    score_contrib = weight / (cls.RRF_K + rank)
                    rrf_scores[c_id] = rrf_scores.get(c_id, 0.0) + score_contrib

            add_ranked_list(exact_list, cls.WEIGHT_EXACT, "exact")
            add_ranked_list(semantic_list, cls.WEIGHT_SEMANTIC, "semantic")
            add_ranked_list(keyword_list, cls.WEIGHT_KEYWORD, "keyword")

            # Sort by fused RRF score descending
            sorted_chunk_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)
            results = []
            for cid in sorted_chunk_ids[:limit]:
                chunk_obj = chunk_map[cid]
                # Normalize RRF score to 0.0 - 1.0 range
                fused_score = min(1.0, round(rrf_scores[cid] * (cls.RRF_K / (cls.WEIGHT_EXACT + cls.WEIGHT_SEMANTIC + cls.WEIGHT_KEYWORD)), 4))
                m_types = "+".join(sorted(match_types[cid]))
                chunk_obj.score = fused_score
                chunk_obj.match_type = m_types
                results.append(chunk_obj)

        if expand_graph_context and results:
            results = await ContextExpander.expand_chunks(session=session, chunks=results)

        return RetrievalResult(
            query=cleaned_query,
            total_results=len(results),
            chunks=results,
        )
