import os
import re
import math
import hashlib
import asyncio
import httpx
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "models/gemini-embedding-2")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768"))

def normalize_l2(vector: List[float]) -> List[float]:
    """L2-normalize a vector to unit length."""
    norm = math.sqrt(sum(x * x for x in vector))
    if norm < 1e-12:
        return vector
    return [x / norm for x in vector]

class BaseEmbeddingProvider(ABC):
    """
    Abstract Base Class for Code Embedding Providers.
    Encapsulates standardized document title/content and query task formatting.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME, dimension: int = EMBEDDING_DIMENSION):
        self._model_name = model_name
        self._dimension = dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    @staticmethod
    def format_document(title: str, text: str) -> str:
        """Format an indexed document into standard representation: title: ... | text: ..."""
        t = title.strip() if title else "code"
        return f"title: {t} | text: {text.strip()}"

    @staticmethod
    def format_query(query: str) -> str:
        """Format a retrieval query into standard representation: task: code retrieval | query: ..."""
        return f"task: code retrieval | query: {query.strip()}"

    def embed_query(self, query: str) -> List[float]:
        """Embed a natural language or code query with standardized task prefix."""
        formatted = self.format_query(query)
        results = self._embed_formatted_batch([formatted])
        return results[0] if results else [0.0] * self._dimension

    def embed_document(self, title: str, content: str) -> List[float]:
        """Embed a single document chunk with structured title metadata."""
        formatted = self.format_document(title, content)
        results = self._embed_formatted_batch([formatted])
        return results[0] if results else [0.0] * self._dimension

    def embed_documents(self, items: List[Tuple[str, str]]) -> List[List[float]]:
        """
        Embed a list of (title, content) tuples in batches.
        """
        if not items:
            return []
        formatted_list = [self.format_document(t, c) for t, c in items]
        return self._embed_formatted_batch(formatted_list)

    @abstractmethod
    def _embed_formatted_batch(self, formatted_texts: List[str]) -> List[List[float]]:
        """Internal batch embedding of pre-formatted text strings."""
        pass


class GeminiEmbeddingProvider(BaseEmbeddingProvider):
    """
    Production Embedding Provider utilizing Google Gemini API (gemini-embedding-2).
    Supports Matryoshka output_dimensionality and batching with backoff.
    """

    BATCH_SIZE: int = 64
    MAX_RETRIES: int = 4

    def __init__(self, api_key: str, model_name: str = EMBEDDING_MODEL_NAME, dimension: int = EMBEDDING_DIMENSION):
        super().__init__(model_name, dimension)
        self.api_key = api_key
        # Clean model name for REST endpoint if prefixed with models/
        clean_model = model_name if not model_name.startswith("models/") else model_name[len("models/"):]
        self.endpoint_url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:batchEmbedContents?key={self.api_key}"

    def _embed_formatted_batch(self, formatted_texts: List[str]) -> List[List[float]]:
        all_embeddings: List[List[float]] = []

        for i in range(0, len(formatted_texts), self.BATCH_SIZE):
            chunk = formatted_texts[i : i + self.BATCH_SIZE]
            clean_model_path = self.model_name if self.model_name.startswith("models/") else f"models/{self.model_name}"

            requests_payload = []
            for text in chunk:
                req = {
                    "model": clean_model_path,
                    "content": {"parts": [{"text": text[:8000]}]},
                }
                if self.dimension:
                    req["outputDimensionality"] = self.dimension
                requests_payload.append(req)

            payload = {"requests": requests_payload}

            # Execute with synchronous httpx and exponential backoff
            embeddings_for_batch = self._execute_request_with_retry(payload, len(chunk))
            all_embeddings.extend(embeddings_for_batch)

        return all_embeddings

    def _execute_request_with_retry(self, payload: dict, expected_count: int) -> List[List[float]]:
        backoff = 1.0
        for attempt in range(self.MAX_RETRIES):
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(self.endpoint_url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        embeddings = []
                        for emb_obj in data.get("embeddings", []):
                            values = emb_obj.get("values", [])
                            # Ensure dimension length and normalize
                            if len(values) > self.dimension:
                                values = values[:self.dimension]
                            elif len(values) < self.dimension:
                                values = values + [0.0] * (self.dimension - len(values))
                            embeddings.append(normalize_l2(values))
                        if len(embeddings) == expected_count:
                            return embeddings
                    elif resp.status_code in (429, 503):
                        # Rate limit or temporary service overload
                        import time
                        time.sleep(backoff)
                        backoff *= 2.0
                    else:
                        break
            except Exception:
                import time
                time.sleep(backoff)
                backoff *= 2.0

        # Fallback to local deterministic vectors if API fails after retries
        local_fallback = DeterministicLocalEmbeddingProvider(self.model_name, self.dimension)
        texts = [r["content"]["parts"][0]["text"] for r in payload["requests"]]
        return local_fallback._embed_formatted_batch(texts)


class DeterministicLocalEmbeddingProvider(BaseEmbeddingProvider):
    """
    Deterministic, zero-dependency local embedding provider for testing and offline CI.
    Generates normalized float vectors of configured dimension using SHA-256 + token frequency hashing.
    """

    def _embed_formatted_batch(self, formatted_texts: List[str]) -> List[List[float]]:
        results: List[List[float]] = []
        dim = self.dimension

        for text in formatted_texts:
            vec = [0.0] * dim
            # Extract tokens
            tokens = re.findall(r"\w+", text.lower())
            if not tokens:
                tokens = ["empty"]

            for token in tokens:
                # Hash token into 3 distinct coordinate slots with pseudo-random weights
                t_bytes = token.encode("utf-8")
                h1 = int(hashlib.sha256(t_bytes).hexdigest(), 16)
                h2 = int(hashlib.md5(t_bytes).hexdigest(), 16)
                h3 = int(hashlib.sha1(t_bytes).hexdigest(), 16)

                idx1 = h1 % dim
                idx2 = h2 % dim
                idx3 = h3 % dim

                w1 = ((h1 >> 8) % 1000) / 500.0 - 1.0
                w2 = ((h2 >> 8) % 1000) / 500.0 - 1.0
                w3 = ((h3 >> 8) % 1000) / 500.0 - 1.0

                vec[idx1] += w1
                vec[idx2] += w2
                vec[idx3] += w3

            results.append(normalize_l2(vec))

        return results


def get_embedding_provider(
    model_name: Optional[str] = None,
    dimension: Optional[int] = None
) -> BaseEmbeddingProvider:
    """
    Factory to retrieve active embedding provider.
    Returns GeminiEmbeddingProvider if GEMINI_API_KEY is present, else DeterministicLocalEmbeddingProvider.
    """
    m_name = model_name or os.getenv("EMBEDDING_MODEL_NAME", EMBEDDING_MODEL_NAME)
    d_dim = dimension or int(os.getenv("EMBEDDING_DIMENSION", str(EMBEDDING_DIMENSION)))
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if api_key:
        return GeminiEmbeddingProvider(api_key=api_key, model_name=m_name, dimension=d_dim)
    return DeterministicLocalEmbeddingProvider(model_name=m_name, dimension=d_dim)
