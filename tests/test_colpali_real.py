"""
Real-PDF smoke test for the QdrantColpaliManager path.

Self-contained: if the `colpali_real_pdf` Qdrant collection is empty (or
missing), this test first builds it from mmore's bundled sample PDFs
(`<mmore>/examples/sample_data/pdf`: COVID / LLaVA / calendar) by running the
ColPali process + index steps, then loads vidore/colpali-v1.3, encodes a few
natural-language queries, retrieves top-K pages, and prints the matches.

So you can just run:

    python tests/test_colpali_real.py

once the server is up and the test env is set up (scripts/setup_test_env.sh).
Needs a GPU. The first run is slow (model download + corpus build); later runs
reuse the populated collection.

If the wire-up + multivector storage are working, queries about COVID hit pages
of the COVID PDF, queries about LLaVA hit pages of the llava-interleave PDF, etc.
"""

import os
import sys
import tempfile
from pathlib import Path

MMORE_SRC = os.environ.get(
    "MMORE_SRC",
    str(Path(__file__).resolve().parents[2] / "mmore" / "src"),
)
sys.path.insert(0, MMORE_SRC)

from mmore.colpali.retriever import (  # noqa: E402
    ColPaliRetriever,
    ColPaliRetrieverConfig,
)


QUERIES = [
    "What are the symptoms of COVID-19?",
    "How does LLaVA handle multiple interleaved images?",
    "When is Christmas?",  # calendar.pdf
]


def _collection_ready(db_path: str, collection: str) -> bool:
    """True if the collection exists and already has points."""
    from qdrant_client import QdrantClient

    client = QdrantClient(url=db_path)
    try:
        if not client.collection_exists(collection):
            return False
        return client.count(collection_name=collection).count > 0
    finally:
        client.close()


def ensure_corpus_indexed(cfg: ColPaliRetrieverConfig) -> None:
    """Build the `colpali_real_pdf` collection from the sample PDFs if empty.

    Runs the same ColPali process -> index pipeline as
    `mmore.colpali.run_process` / `run_index`, pointed at the running Qdrant
    server, so the query below has something to retrieve.
    """
    if _collection_ready(cfg.db_path, cfg.collection_name):
        print(f"Collection '{cfg.collection_name}' already populated — skipping build.")
        return

    pdf_dir = Path(MMORE_SRC).parent / "examples" / "sample_data" / "pdf"
    if not pdf_dir.is_dir():
        raise SystemExit(
            f"Sample PDFs not found at {pdf_dir}. "
            "Point MMORE_SRC at your mmore/src checkout."
        )

    print(
        f"Collection '{cfg.collection_name}' is empty — building it from "
        f"{pdf_dir} (process + index, GPU)...\n"
    )
    workdir = Path(tempfile.mkdtemp(prefix="colpali_corpus_"))

    process_cfg = workdir / "process.yml"
    process_cfg.write_text(
        "data_path:\n"
        f'  - "{pdf_dir}"\n'
        f'output_path: "{workdir}"\n'
        f'model_name: "{cfg.model_name}"\n'
        "skip_already_processed: true\n"
        "num_workers: 2\n"
        "batch_size: 8\n"
    )

    index_cfg = workdir / "index.yml"
    index_cfg.write_text(
        f'parquet_path: "{workdir}/pdf_page_objects.parquet"\n'
        "milvus:\n"
        "  backend: qdrant\n"
        f'  db_path: "{cfg.db_path}"\n'
        f'  collection_name: "{cfg.collection_name}"\n'
        f"  dim: {cfg.dim}\n"
        "  create_collection: true\n"
        f'  metric_type: "{cfg.metric_type}"\n'
    )

    from mmore.colpali.run_process import run_process

    run_process(str(process_cfg))

    from mmore.colpali.run_index import index

    index(str(index_cfg))
    print(f"\nCorpus built into '{cfg.collection_name}'.\n")


def main() -> None:
    cfg = ColPaliRetrieverConfig(
        db_path="http://127.0.0.1:6333",
        collection_name="colpali_real_pdf",
        backend="qdrant",
        model_name="vidore/colpali-v1.3",
        top_k=3,
        dim=128,
        metric_type="IP",
    )

    ensure_corpus_indexed(cfg)

    print("\nLoading ColPali retriever (model + Qdrant client)...")
    retriever = ColPaliRetriever.from_config(cfg)
    print("Ready.\n")

    for q in QUERIES:
        print(f"\nQ: {q}")
        docs = retriever._get_relevant_documents(q)
        if not docs:
            print("   (no hits)")
            continue
        for d in docs:
            md = d.metadata
            pdf_name = md.get("pdf_name", "?")
            page = md.get("page_number", "?")
            score = md.get("similarity", float("nan"))
            print(f"   rank={md.get('rank'):>2}  score={score:>8.3f}  {pdf_name} p{page}")

    print("\nReal-PDF smoke test done.\n")


if __name__ == "__main__":
    main()
