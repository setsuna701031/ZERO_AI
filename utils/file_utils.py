from __future__ import annotations

import shutil
from pathlib import Path

from config import BACKUP_DIR, BASE_DIR, MAX_READ_CHARS


TEXT_EXTENSIONS = {
    ".py", ".txt", ".md", ".json", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".log", ".csv", ".bat", ".ps1", ".js", ".ts", ".html", ".css",
}



def resolve_user_path(user_path: str) -> Path:
    user_path = user_path.strip()
    if not user_path:
        return BASE_DIR

    path = Path(user_path)
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    return path



def is_text_like_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS



def read_text_file(path: Path) -> str:
    data = path.read_text(encoding="utf-8", errors="ignore")
    if len(data) > MAX_READ_CHARS:
        data = data[:MAX_READ_CHARS] + "\n\n[內容過長，已截斷]"
    return data



def write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")



def backup_file(path: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"{path.name}.bak"
    shutil.copy2(path, backup_path)
    return backup_path