"""Factories that turn configuration into ChatModel / Embedder objects.

Provider SDKs are imported lazily so the rest of the backend (and its tests)
work without them installed.
"""

from __future__ import annotations

import numpy as np

from meetwise.config import Settings
from meetwise.llm.base import ChatModel, Embedder
from meetwise.llm.hashing import HashingEmbedder


class ProviderConfigError(RuntimeError):
    pass


class LangChainChatModel:
    """Adapts any LangChain chat model to the ChatModel protocol."""

    def __init__(self, name: str, chat_model) -> None:
        self.name = name
        self._chat = chat_model

    def complete(self, system: str, user: str) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        reply = self._chat.invoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        content = reply.content
        if isinstance(content, str):
            return content
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )


class LangChainEmbedder:
    def __init__(self, name: str, embeddings) -> None:
        self.name = name
        self._emb = embeddings

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        return np.asarray(self._emb.embed_documents(texts), dtype=np.float32)


def build_chat_model(settings: Settings) -> ChatModel:
    provider = settings.llm_provider.strip().lower()
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        chat = ChatOllama(
            model=settings.ollama_chat_model,
            base_url=settings.ollama_base_url,
            temperature=0,
            format="json",
            think=False,
            reasoning=False,
        )
        return LangChainChatModel(f"ollama:{settings.ollama_chat_model}", chat)
    if provider == "groq":
        if not settings.groq_api_key:
            raise ProviderConfigError(
                "GROQ_API_KEY must be set when MEETWISE_LLM_PROVIDER=groq."
            )
        from langchain_groq import ChatGroq

        chat = ChatGroq(
            model=settings.groq_chat_model,
            api_key=settings.groq_api_key,
            temperature=0,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
        return LangChainChatModel(f"groq:{settings.groq_chat_model}", chat)
    raise ProviderConfigError(
        f"Unknown LLM provider '{settings.llm_provider}'. Use 'ollama' or 'groq'."
    )


def build_embedder(settings: Settings) -> Embedder:
    provider = settings.embedding_provider.strip().lower()
    if provider == "ollama":
        from langchain_ollama import OllamaEmbeddings

        emb = OllamaEmbeddings(
            model=settings.ollama_embed_model, base_url=settings.ollama_base_url
        )
        return LangChainEmbedder(f"ollama:{settings.ollama_embed_model}", emb)
    if provider == "hash":
        return HashingEmbedder()
    if provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        emb = GoogleGenerativeAIEmbeddings(model="gemini-embedding-2-preview")
        return LangChainEmbedder(f"gemini:{settings.gemini_embed_model}", emb)
    raise ProviderConfigError(
        f"Unknown embedding provider '{settings.embedding_provider}'. Use 'ollama' or 'hash'."
    )
