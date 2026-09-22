from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.db.models import Symbol, Dependency
from packages.code_intel.models import RankedChunk, GraphContextSummary

class ContextExpander:
    """
    AST & Dependency Graph Context Expander.
    Enriches retrieved code chunks with 1-hop upstream callers and downstream callees.
    """

    @classmethod
    async def expand_chunks(
        cls,
        session: AsyncSession,
        chunks: List[RankedChunk]
    ) -> List[RankedChunk]:
        symbol_ids = [c.symbol_id for c in chunks if c.symbol_id]
        if not symbol_ids:
            return chunks

        # Fetch incoming dependencies (Callers)
        in_stmt = select(Dependency).where(Dependency.callee_symbol_id.in_(symbol_ids))
        in_res = await session.execute(in_stmt)
        in_deps = in_res.scalars().all()

        # Fetch outgoing dependencies (Callees)
        out_stmt = select(Dependency).where(Dependency.caller_symbol_id.in_(symbol_ids))
        out_res = await session.execute(out_stmt)
        out_deps = out_res.scalars().all()

        # Collect all related symbol IDs to resolve their FQNs/signatures
        related_sym_ids = set()
        for d in in_deps:
            related_sym_ids.add(d.caller_symbol_id)
        for d in out_deps:
            related_sym_ids.add(d.callee_symbol_id)

        sym_map: Dict[str, Symbol] = {}
        if related_sym_ids:
            sym_stmt = select(Symbol).where(Symbol.id.in_(list(related_sym_ids)))
            sym_res = await session.execute(sym_stmt)
            for s in sym_res.scalars().all():
                sym_map[s.id] = s

        # Build mapping for each target symbol_id
        caller_map: Dict[str, List[str]] = {}
        for d in in_deps:
            s_obj = sym_map.get(d.caller_symbol_id)
            if s_obj:
                sig = f"{s_obj.fully_qualified_name} ({s_obj.kind})"
                caller_map.setdefault(d.callee_symbol_id, []).append(sig)

        callee_map: Dict[str, List[str]] = {}
        for d in out_deps:
            s_obj = sym_map.get(d.callee_symbol_id)
            if s_obj:
                sig = f"{s_obj.fully_qualified_name} ({s_obj.kind})"
                callee_map.setdefault(d.caller_symbol_id, []).append(sig)

        for chunk in chunks:
            if chunk.symbol_id:
                callers = caller_map.get(chunk.symbol_id, [])
                callees = callee_map.get(chunk.symbol_id, [])
                chunk.graph_context = GraphContextSummary(
                    symbol_fqn=chunk.symbol_fqn or "",
                    kind=chunk.symbol_kind or "symbol",
                    callers=list(set(callers))[:5],
                    callees=list(set(callees))[:5],
                    file_path=chunk.file_path,
                )

        return chunks
