from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = DATA_DIR / "logs"
MEMORY_DIR = DATA_DIR / "memory"
BACKUP_DIR = DATA_DIR / "backups"
WORKSPACE_DIR = DATA_DIR / "workspace"

for folder in [DATA_DIR, LOG_DIR, MEMORY_DIR, BACKUP_DIR, WORKSPACE_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

APP_NAME = "ZERO AI"
APP_VERSION = "0.1.0"

# 本地模型設定（預設 Ollama 相容接口）
LLM_ENABLED = True
LLM_API_URL = "http://127.0.0.1:11434/api/generate"
LLM_MODEL = "qwen:7b"
LLM_TIMEOUT = 120

# 寫檔 / 執行安全限制
SAFE_MODE = True
ALLOWED_WRITE_DIRS = [
    str(WORKSPACE_DIR.resolve()),
]
ALLOWED_RUN_DIRS = [
    str(WORKSPACE_DIR.resolve()),
]
MAX_READ_CHARS = 20000
MAX_SEARCH_RESULTS = 20
PYTHON_EXEC_TIMEOUT = 20

# 記憶
MEMORY_FILE = MEMORY_DIR / "summaries.json"
HISTORY_FILE = MEMORY_DIR / "history.json"

# CLI
CLI_PROMPT = "ZERO> "