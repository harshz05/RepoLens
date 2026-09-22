import re
from typing import List, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.db.models import File, Symbol
from packages.code_intel.models import CitationRecord

CITATION_REGEX = re.compile(r"\[([a-zA-Z0-9_\-\.\/\+]+):(\d+)(?:-(\d+))?\]")

class CitationValidator:
    """
    Validates and enriches [file_path:start_line-end_line] citations extracted from LLM responses
    against real database AST symbols and files.
    """

    @classmethod
    async def extract_and_validate(
        cls,
        session: AsyncSession,
        repository_version_id: str,
        response_text: str,
    ) -> List[CitationRecord]:
        matches = CITATION_REGEX.findall(response_text)
        if not matches:
            return []

        # Fetch all files for this version
        file_stmt = select(File).where(File.repository_version_id == repository_version_id)
        file_res = await session.execute(file_stmt)
        files = file_res.scalars().all()
        file_path_map = {f.path: f for f in files}

        verified_citations: List[CitationRecord] = []
        seen_keys = set()

        for file_path, start_str, end_str in matches:
            start_line = int(start_str)
            end_line = int(end_str) if end_str else start_line

            # Normalize path lookup (strip leading slashes or ./ prefixes)
            normalized_path = file_path.lstrip("./").lstrip("/")
            file_obj = file_path_map.get(normalized_path) or file_path_map.get(file_path)

            if not file_obj:
                # Also check suffix match (e.g. if LLM wrote auth.py instead of services/auth.py)
                for f_p, f_o in file_path_map.items():
                    if f_p.endswith(f"/{normalized_path}") or f_p.endswith(normalized_path):
                        file_obj = f_o
                        break

            if not file_obj:
                # Citation refers to non-existent file -> rejected
                continue

            # Bounds check
            start_line = max(1, min(start_line, file_obj.line_count))
            end_line = max(start_line, min(end_line, file_obj.line_count))

            cit_key = (file_obj.id, start_line, end_line)
            if cit_key in seen_keys:
                continue
            seen_keys.add(cit_key)

            # Find matching symbol in this line range
            sym_stmt = (
                select(Symbol)
                .where(
                    Symbol.file_id == file_obj.id,
                    Symbol.start_line <= end_line,
                    Symbol.end_line >= start_line,
                )
            )
            sym_res = await session.execute(sym_stmt)
            sym = sym_res.scalars().first()

            verified_citations.append(
                CitationRecord(
                    file_path=file_obj.path,
                    start_line=start_line,
                    end_line=end_line,
                    snippet=f"{file_obj.path} (lines {start_line}-{end_line})",
                    confidence_score=1.0,
                    symbol_name=sym.name if sym else None,
                    file_id=file_obj.id,
                    symbol_id=sym.id if sym else None,
                )
            )

        return verified_citations
