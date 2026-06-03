"""
End-to-end smoke test of the mmore qdrant adapter against a running
Qdrant *server* (not local-mode).

Equivalent to test_qdrant_pipeline.py from the PR branch, but the URI is
an HTTP URL instead of a temp directory. Validates that the same
QdrantMilvusClient code path works for both modes.

Usage (from any cwd, once the venv exists and qdrant is running):
    bench/mmore-qdrant/.venv/bin/python bench/test_qdrant_server.py

Optional: set QDRANT_URL to override the default.
"""

import os
from typing import Dict, List

from langchain_milvus.utils.sparse import BaseSparseEmbedding

import mmore.rag.model.sparse.base as _sparse_base
from mmore.index.indexer import DBConfig, Indexer, IndexerConfig
from mmore.rag.model.dense.base import DenseModelConfig
from mmore.rag.model.sparse.base import SparseModelConfig
from mmore.rag.retriever import Retriever, RetrieverConfig
from mmore.type import MultimodalSample


class StubSparseEmbedding(BaseSparseEmbedding):
    def embed_query(self, query: str) -> Dict[int, float]:
        return {hash(w) % 512: 1.0 for w in query.split()}

    def embed_documents(self, texts: List[str]) -> List[Dict[int, float]]:
        return [self.embed_query(t) for t in texts]


@classmethod  # type: ignore[misc]
def _stub_from_config(cls, _cfg):
    return StubSparseEmbedding()


_sparse_base.SparseModel.from_config = _stub_from_config


QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
COLLECTION = "smoke_test_server"

DOCS = [
    MultimodalSample(text="Barack Obama was born on August 4, 1961, in Honolulu, Hawaii.", modalities=[], metadata={"source": "wikipedia"}),
    MultimodalSample(text="Google was founded by Larry Page and Sergey Brin in September 1998.", modalities=[], metadata={"source": "wikipedia"}),
    MultimodalSample(text="The Eiffel Tower is located on the Champ de Mars in Paris, France.", modalities=[], metadata={"source": "wikipedia"}),
    MultimodalSample(text="The Python programming language was created by Guido van Rossum.", modalities=[], metadata={"source": "wikipedia"}),
    MultimodalSample(text="Mount Everest is the world's highest mountain above sea level.", modalities=[], metadata={"source": "wikipedia"}),
]

QUERIES = [
    "When was Barack Obama born?",
    "Who founded Google?",
    "Where is the Eiffel Tower located?",
]


def main() -> None:
    print(f"\nQdrant server: {QDRANT_URL}")
    print(f"Collection:    {COLLECTION}\n")

    cfg = IndexerConfig(
        dense_model=DenseModelConfig(model_name="debug", is_multimodal=False),
        sparse_model=SparseModelConfig(model_name="splade", is_multimodal=False),
        db=DBConfig(backend="qdrant", uri=QDRANT_URL, name="bench_db"),
    )

    print("[1/3] Indexing 5 toy documents...")
    indexer = Indexer.from_config(cfg)
    n = indexer.index_documents(DOCS, collection_name=COLLECTION)
    print(f"      Inserted: {n} chunks")

    print("\n[2/3] Retrieval against server...")
    ret_cfg = RetrieverConfig(
        db=DBConfig(backend="qdrant", uri=QDRANT_URL, name="bench_db"),
        k=2,
        collection_name=COLLECTION,
        reranker_model_name=None,
    )
    retriever = Retriever.from_config(ret_cfg)

    for q in QUERIES:
        hits = retriever.retrieve(q, collection_name=COLLECTION, k=2)
        top = hits[0]["entity"]["text"][:80] if hits else "(no results)"
        print(f"\n  Q: {q}\n  A: {top}...")

    print("\n[3/3] Index metadata round-trip...")
    models = retriever.backend.describe_models(COLLECTION)
    print(f"      dense  model:  {models['dense'].get('model_name')}")
    print(f"      sparse model:  {models['sparse'].get('model_name')}")

    print("\nServer-mode smoke test PASSED.\n")


if __name__ == "__main__":
    main()
