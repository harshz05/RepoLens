import math
import pytest
from packages.code_intel.embeddings.provider import (
    BaseEmbeddingProvider,
    DeterministicLocalEmbeddingProvider,
    GeminiEmbeddingProvider,
    get_embedding_provider,
    normalize_l2,
)

def test_input_formatting():
    # 1. Document representation formatting: title: ... | text: ...
    doc_formatted = BaseEmbeddingProvider.format_document("services/auth.py | Symbol: AuthService", "class AuthService: pass")
    assert doc_formatted == "title: services/auth.py | Symbol: AuthService | text: class AuthService: pass"

    # 2. Query representation formatting: task: code retrieval | query: ...
    query_formatted = BaseEmbeddingProvider.format_query("how is user auth handled")
    assert query_formatted == "task: code retrieval | query: how is user auth handled"

def test_deterministic_provider_normalization_and_dimensions():
    for dim in [512, 768, 1536]:
        provider = DeterministicLocalEmbeddingProvider(dimension=dim)
        assert provider.dimension == dim

        vec = provider.embed_query("find user by email")
        assert len(vec) == dim
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-4

def test_deterministic_provider_consistency_and_similarity():
    provider = DeterministicLocalEmbeddingProvider(dimension=768)

    # Identical queries produce identical vectors
    vec1 = provider.embed_query("authenticate user token")
    vec2 = provider.embed_query("authenticate user token")
    assert vec1 == vec2

    # Similar queries produce higher cosine similarity than unrelated queries
    vec_related = provider.embed_query("verify user authentication token")
    vec_unrelated = provider.embed_query("render database table html canvas")

    def dot_product(v1, v2):
        return sum(a * b for a, b in zip(v1, v2))

    sim_related = dot_product(vec1, vec_related)
    sim_unrelated = dot_product(vec1, vec_unrelated)

    assert sim_related > sim_unrelated

def test_batch_document_embedding():
    provider = DeterministicLocalEmbeddingProvider(dimension=768)
    docs = [
        ("file1.py | Func: foo", "def foo(): return 1"),
        ("file2.py | Func: bar", "def bar(): return 2"),
    ]
    vectors = provider.embed_documents(docs)
    assert len(vectors) == 2
    assert len(vectors[0]) == 768
    assert len(vectors[1]) == 768

def test_get_embedding_provider_factory():
    provider = get_embedding_provider(dimension=768)
    assert isinstance(provider, BaseEmbeddingProvider)
    assert provider.dimension == 768
