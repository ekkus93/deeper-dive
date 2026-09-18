from __future__ import annotations

from typing import Any

import pytest

from deeper_dive.embedding_backends import (
    OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)


def test_openai_embedding_adapter_contract_without_credentials() -> None:
    calls: list[tuple[str, dict[str, Any], dict[str, str], float]] = []

    def post(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float):
        calls.append((url, payload, headers, timeout))
        return {"data": [{"index": 1, "embedding": [0.3, 0.4]}, {"index": 0, "embedding": [0.1, 0.2]}]}

    provider = OpenAIEmbeddingProvider(
        api_key="test-key", model="text-embedding-test", dimensions=2, post_json=post
    )
    assert provider.embed(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]
    assert provider.metadata.provider == "openai"
    assert calls[0][0].endswith("/v1/embeddings")
    assert calls[0][1] == {"model": "text-embedding-test", "input": ["a", "b"]}
    assert calls[0][2]["Authorization"] == "Bearer test-key"


def test_ollama_embedding_adapter_contract_without_model() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def post(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float):
        calls.append((url, payload))
        return {"embeddings": [[1, 2], [3, 4]]}

    provider = OllamaEmbeddingProvider(model="local-test", dimensions=2, post_json=post)
    assert provider.embed(["a", "b"]) == [[1.0, 2.0], [3.0, 4.0]]
    assert provider.metadata.provider == "ollama"
    assert calls == [("http://127.0.0.1:11434/api/embed", {"model": "local-test", "input": ["a", "b"]})]


def test_sentence_transformer_style_adapter_uses_injected_encoder() -> None:
    provider = SentenceTransformerEmbeddingProvider(
        model="tiny-local", dimensions=3, encoder=lambda texts: [[len(text), 1, 2] for text in texts]
    )
    assert provider.embed(["ab", "c"]) == [[2.0, 1.0, 2.0], [1.0, 1.0, 2.0]]
    assert provider.metadata.provider == "sentence-transformers"


def test_backends_reject_wrong_vector_dimensions() -> None:
    provider = OllamaEmbeddingProvider(
        model="bad", dimensions=2, post_json=lambda *_: {"embeddings": [[1.0]]}
    )
    with pytest.raises(ValueError, match="dimensions"):
        provider.embed(["x"])
