"""Initial remote and local embedding provider adapters."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.request import Request, urlopen

from deeper_dive.embeddings import EmbeddingModel

JsonPost = Callable[[str, dict[str, Any], dict[str, str], float], dict[str, Any]]


def _post_json(
    url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured provider URL
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("embedding provider returned a non-object response")
    return value


def _vectors(value: Any, *, dimensions: int) -> list[list[float]]:
    if not isinstance(value, list):
        raise ValueError("embedding provider response is missing vectors")
    vectors: list[list[float]] = []
    for vector in value:
        if not isinstance(vector, list) or len(vector) != dimensions:
            raise ValueError("embedding vector dimensions do not match model metadata")
        vectors.append([float(item) for item in vector])
    return vectors


class OpenAIEmbeddingProvider:
    """OpenAI-compatible embeddings adapter using the documented /v1/embeddings shape."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
        post_json: JsonPost = _post_json,
    ) -> None:
        self._metadata = EmbeddingModel("openai", model, dimensions)
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._post = post_json

    @property
    def metadata(self) -> EmbeddingModel:
        return self._metadata

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._post(
            f"{self._base_url}/embeddings",
            {"model": self.metadata.model, "input": texts},
            {"Authorization": f"Bearer {self._api_key}"},
            self._timeout,
        )
        data = response.get("data")
        if not isinstance(data, list):
            raise ValueError("OpenAI embedding response is missing data")
        ordered = sorted(data, key=lambda item: int(item["index"]))
        return _vectors(
            [item.get("embedding") for item in ordered], dimensions=self.metadata.dimensions
        )


class OllamaEmbeddingProvider:
    """Ollama adapter for its batch-capable /api/embed endpoint."""

    def __init__(
        self,
        *,
        model: str,
        dimensions: int,
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 30.0,
        post_json: JsonPost = _post_json,
    ) -> None:
        self._metadata = EmbeddingModel("ollama", model, dimensions)
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._post = post_json

    @property
    def metadata(self) -> EmbeddingModel:
        return self._metadata

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._post(
            f"{self._base_url}/api/embed",
            {"model": self.metadata.model, "input": texts},
            {},
            self._timeout,
        )
        return _vectors(response.get("embeddings"), dimensions=self.metadata.dimensions)


class SentenceTransformerEmbeddingProvider:
    """Local sentence-transformer-style adapter with lazy optional dependency loading."""

    def __init__(
        self,
        *,
        model: str,
        dimensions: int,
        encoder: Callable[[list[str]], Any] | None = None,
    ) -> None:
        self._metadata = EmbeddingModel("sentence-transformers", model, dimensions)
        if encoder is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "local embeddings require the optional sentence-transformers package"
                ) from exc
            instance = SentenceTransformer(model)
            encoder = instance.encode
        self._encoder = encoder

    @property
    def metadata(self) -> EmbeddingModel:
        return self._metadata

    def embed(self, texts: list[str]) -> list[list[float]]:
        raw = self._encoder(texts)
        if hasattr(raw, "tolist"):
            raw = raw.tolist()
        return _vectors(raw, dimensions=self.metadata.dimensions)
