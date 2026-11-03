"""Runtime configuration, read from environment variables.

LLM (chat) and embedding providers are selected independently because
Groq offers chat completions but no embeddings endpoint.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # "ollama" or "groq"
    llm_provider: str = os.getenv("MEETWISE_LLM_PROVIDER", "ollama")
    # "ollama" or "hash" (offline lexical fallback, useful for development and tests)
    embedding_provider: str = os.getenv("MEETWISE_EMBEDDING_PROVIDER", "ollama")

    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_chat_model: str = os.getenv("MEETWISE_OLLAMA_CHAT_MODEL", "llama3.1:8b")
    ollama_embed_model: str = os.getenv(
        "MEETWISE_OLLAMA_EMBED_MODEL", "nomic-embed-text"
    )

    groq_api_key: str | None = os.getenv("GROQ_API_KEY")
    groq_chat_model: str = os.getenv(
        "MEETWISE_GROQ_CHAT_MODEL", "llama-3.3-70b-versatile"
    )

    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    gemini_embed_model: str = os.getenv("MEETWISE_GEMINI_EMBED_MODEL")

    db_path: str = os.getenv("MEETWISE_DB_PATH", "meetwise.db")
    # Approximate character budget per LLM call. Longer transcripts are windowed.
    window_chars: int = _env_int("MEETWISE_WINDOW_CHARS", 12000)
    # Total extraction passes allowed when verification finds unsupported items.
    max_extraction_attempts: int = _env_int("MEETWISE_MAX_EXTRACTION_ATTEMPTS", 2)


settings = Settings()
