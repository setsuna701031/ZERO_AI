import os
from dataclasses import dataclass


@dataclass
class Settings:
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1:latest")
    searxng_url: str = os.getenv("SEARXNG_URL", "http://127.0.0.1:8888")
    max_file_chars: int = int(os.getenv("MAX_FILE_CHARS", "12000"))
    max_observation_chars: int = int(os.getenv("MAX_OBSERVATION_CHARS", "16000"))
    project_scan_limit: int = int(os.getenv("PROJECT_SCAN_LIMIT", "200"))
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "90"))


settings = Settings()