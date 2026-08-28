import re
import unicodedata
from pathlib import Path


def sanitize_filename(name: str, max_length: int = 120) -> str:
    """
    Sanitize string to be safe for filesystem naming across OS (macOS, Windows, Linux),
    while preserving Persian/Arabic/Unicode alphabets and numbers.
    """
    if not name:
        return "untitled"

    # Normalize unicode
    name = unicodedata.normalize("NFC", str(name)).strip()

    # Replace forbidden filesystem characters: / \ : * ? " < > | \0
    name = re.sub(r'[\/\\:\*\?"<>\|\x00]', '_', name)

    # Collapse multiple whitespaces / underscores
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(r'_+', '_', name)
    name = name.strip(' ._')

    # Truncate length if needed
    if len(name) > max_length:
        name = name[:max_length].strip(' ._')

    return name or "untitled"


def format_bytes(size: int | float | None) -> str:
    """Format bytes into human-readable representation."""
    if size is None or size <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    val = float(size)
    while val >= 1024.0 and unit_index < len(units) - 1:
        val /= 1024.0
        unit_index += 1
    return f"{val:.2f} {units[unit_index]}"


def format_duration(seconds: int | float | None) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    if not seconds or seconds <= 0:
        return "00:00"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path
