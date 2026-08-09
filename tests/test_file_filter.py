import pytest
from pathlib import Path
from packages.code_intel.file_filter import is_text_file, get_file_language, scan_repository_files

def test_get_file_language():
    assert get_file_language(Path("app.py")) == "python"
    assert get_file_language(Path("index.ts")) == "typescript"
    assert get_file_language(Path("Component.tsx")) == "typescript"
    assert get_file_language(Path("main.go")) == "go"
    assert get_file_language(Path("unknown.xyz")) == "text"

def test_scan_repository_files(tmp_path):
    # Create sample repository structure
    (tmp_path / "src").mkdir()
    (tmp_path / "node_modules").mkdir()

    # Valid python file
    py_file = tmp_path / "src" / "main.py"
    py_file.write_text("def hello():\n    print('world')\n", encoding="utf-8")

    # Ignored directory file
    nm_file = tmp_path / "node_modules" / "package.json"
    nm_file.write_text("{}", encoding="utf-8")

    # Binary file
    bin_file = tmp_path / "image.png"
    bin_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")

    scanned = scan_repository_files(tmp_path)
    scanned_paths = [path.as_posix() for path, lang, lines, size in scanned]

    assert "src/main.py" in scanned_paths
    assert "node_modules/package.json" not in scanned_paths
    assert "image.png" not in scanned_paths
