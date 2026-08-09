import os
from pathlib import Path
from typing import Dict, List, Set, Tuple

MAX_FILE_SIZE_BYTES = 1024 * 1024  # 1 MB limit per file

IGNORED_DIRECTORIES: Set[str] = {
    ".git",
    "node_modules",
    ".next",
    "dist",
    "build",
    "out",
    ".cache",
    ".turbo",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "ENV",
    ".idea",
    ".vscode",
    "target",
    "vendor",
    "coverage",
    "htmlcov",
    ".eggs",
}

IGNORED_EXTENSIONS: Set[str] = {
    # Binaries & Executables
    ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".pyc", ".pyo", ".pyd", ".class",
    # Archives
    ".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz", ".iso",
    # Media
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".mp3", ".mp4", ".mov", ".wav", ".pdf",
    # Fonts
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    # Databases & Heavy Data
    ".db", ".sqlite", ".sqlite3", ".dump", ".sql.gz", ".parquet",
}

EXTENSION_TO_LANGUAGE: Dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".sh": "bash",
    ".ps1": "powershell",
}

def is_text_file(file_path: Path) -> bool:
    """Check if a file is readable text by reading the first 1024 bytes."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return False
            return True
    except Exception:
        return False

def get_file_language(file_path: Path) -> str:
    """Infer file language from extension."""
    ext = file_path.suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(ext, "text")

def scan_repository_files(repo_dir: Path) -> List[Tuple[Path, str, int, int]]:
    """
    Safely scan repository files.
    Returns list of tuples: (relative_path, language, line_count, byte_size)
    """
    scanned_files: List[Tuple[Path, str, int, int]] = []

    for root, dirs, files in os.walk(repo_dir):
        # Filter out ignored directories in-place
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES]

        for file_name in files:
            full_path = Path(root) / file_name
            ext = full_path.suffix.lower()

            if ext in IGNORED_EXTENSIONS:
                continue

            try:
                stat = full_path.stat()
                byte_size = stat.st_size

                if byte_size > MAX_FILE_SIZE_BYTES or byte_size == 0:
                    continue

                if not is_text_file(full_path):
                    continue

                rel_path = full_path.relative_to(repo_dir)
                language = get_file_language(full_path)

                # Count lines safely
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    line_count = sum(1 for _ in f)

                scanned_files.append((rel_path, language, line_count, byte_size))

            except Exception:
                continue

    return scanned_files
