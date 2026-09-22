import re
from typing import List, Optional, Set, Tuple
from packages.code_intel.models import ExtractedFileContext, ExtractedSymbol, ExtractedChunk

def estimate_tokens(text: str) -> int:
    """Accurately estimate token count for code (approx 3.8 - 4 chars per token)."""
    if not text:
        return 0
    # Split by whitespace, punctuation, and camelCase boundaries
    tokens = re.findall(r"\w+|[^\w\s]", text)
    return max(1, len(tokens))

class ASTAwareChunker:
    """
    AST-Aware Code Chunker.
    Chunks code along syntactic symbol boundaries (functions, classes, methods)
    and module-level interstitials, preserving signatures, docstrings, and enclosing scopes.
    """

    MAX_CHUNK_TOKENS: int = 1000
    SUB_CHUNK_SIZE_LINES: int = 70
    SUB_CHUNK_OVERLAP_LINES: int = 10

    @classmethod
    def chunk_file(
        cls,
        code_str: str,
        file_path: str,
        language: str,
        context: Optional[ExtractedFileContext] = None,
        symbol_db_map: Optional[dict[str, str]] = None,
    ) -> List[ExtractedChunk]:
        """
        Chunk a file into semantic code chunks linked to AST symbols.
        """
        lines = code_str.splitlines()
        total_lines = len(lines)
        if total_lines == 0:
            return []

        chunks: List[ExtractedChunk] = []
        covered_lines: Set[int] = set()

        symbols: List[ExtractedSymbol] = []
        if context and context.symbols:
            symbols = context.symbols

        # Sort symbols by start line, then by descending length (outer classes first)
        sorted_symbols = sorted(
            symbols,
            key=lambda s: (s.start_line, -(s.end_line - s.start_line))
        )

        for sym in sorted_symbols:
            s_start = max(1, sym.start_line)
            s_end = min(total_lines, sym.end_line)
            if s_start > s_end:
                continue

            symbol_lines = lines[s_start - 1 : s_end]
            raw_content = "\n".join(symbol_lines)
            tokens = estimate_tokens(raw_content)

            meta_title = f"{file_path} | Symbol: {sym.fully_qualified_name} ({sym.kind})"
            header = f"// File: {file_path} | {sym.kind.upper()}: {sym.fully_qualified_name}\n"
            if sym.signature:
                header += f"// Signature: {sym.signature}\n"

            formatted_content = header + raw_content
            sym_id = symbol_db_map.get(sym.fully_qualified_name) if symbol_db_map else None

            # If symbol is within max token limit, add as single chunk
            if tokens <= cls.MAX_CHUNK_TOKENS:
                chunks.append(
                    ExtractedChunk(
                        file_path=file_path,
                        start_line=s_start,
                        end_line=s_end,
                        content=formatted_content,
                        token_count=estimate_tokens(formatted_content),
                        language=language,
                        metadata_title=meta_title,
                        symbol_id=sym_id,
                        symbol_fqn=sym.fully_qualified_name,
                        symbol_kind=sym.kind,
                    )
                )
                for l in range(s_start, s_end + 1):
                    covered_lines.add(l)
            else:
                # Sub-chunk massive function/class into overlapping windows
                curr_start = s_start
                part_idx = 1
                while curr_start <= s_end:
                    curr_end = min(s_end, curr_start + cls.SUB_CHUNK_SIZE_LINES)
                    sub_lines = lines[curr_start - 1 : curr_end]
                    sub_raw = "\n".join(sub_lines)
                    sub_header = f"// File: {file_path} | {sym.kind.upper()}: {sym.fully_qualified_name} (Part {part_idx}, lines {curr_start}-{curr_end})\n"
                    sub_content = sub_header + sub_raw
                    chunks.append(
                        ExtractedChunk(
                            file_path=file_path,
                            start_line=curr_start,
                            end_line=curr_end,
                            content=sub_content,
                            token_count=estimate_tokens(sub_content),
                            language=language,
                            metadata_title=f"{meta_title} [Part {part_idx}]",
                            symbol_id=sym_id,
                            symbol_fqn=sym.fully_qualified_name,
                            symbol_kind=sym.kind,
                        )
                    )
                    for l in range(curr_start, curr_end + 1):
                        covered_lines.add(l)

                    if curr_end >= s_end:
                        break
                    curr_start = curr_end - cls.SUB_CHUNK_OVERLAP_LINES
                    part_idx += 1

        # Interstitial chunks: Capture non-symbol lines (imports, top-level scripts, constants)
        uncovered_ranges: List[Tuple[int, int]] = []
        range_start: Optional[int] = None

        for l in range(1, total_lines + 1):
            if l not in covered_lines:
                if range_start is None:
                    range_start = l
            else:
                if range_start is not None:
                    uncovered_ranges.append((range_start, l - 1))
                    range_start = None
        if range_start is not None:
            uncovered_ranges.append((range_start, total_lines))

        for r_start, r_end in uncovered_ranges:
            gap_lines = lines[r_start - 1 : r_end]
            gap_text = "\n".join(gap_lines).strip()
            # Only create chunk if contains meaningful non-whitespace code
            if gap_text and len(gap_text) > 10:
                header = f"// File: {file_path} | Module Scope (lines {r_start}-{r_end})\n"
                content = header + "\n".join(gap_lines)
                meta_title = f"{file_path} | Module Scope (lines {r_start}-{r_end})"
                chunks.append(
                    ExtractedChunk(
                        file_path=file_path,
                        start_line=r_start,
                        end_line=r_end,
                        content=content,
                        token_count=estimate_tokens(content),
                        language=language,
                        metadata_title=meta_title,
                        symbol_id=None,
                        symbol_fqn=None,
                        symbol_kind="module_scope",
                    )
                )

        # Sort all chunks by start_line
        chunks.sort(key=lambda c: c.start_line)
        return chunks
