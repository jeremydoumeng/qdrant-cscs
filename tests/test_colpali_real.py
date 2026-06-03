"""
Real-PDF smoke test for the new QdrantColpaliManager path.

Runs after `mmore colpali process` + `mmore colpali index` have populated the
`colpali_real_pdf` Qdrant collection. Loads vidore/colpali-v1.3, encodes a
handful of natural-language queries, retrieves top-K pages, and prints the
match for visual sanity checking.

If the wire-up + multivector storage are working, queries about COVID should
hit pages of the COVID PDF, queries about LLaVA should hit pages of the
llava-interleave PDF, etc.
"""

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path("os.environ.get("MMORE_SRC", str(Path(__file__).resolve().parents[2] / "mmore/src"))")
    ),
)

from mmore.colpali.retriever import (  # noqa: E402
    ColPaliRetriever,
    ColPaliRetrieverConfig,
)


QUERIES = [
    "What are the symptoms of COVID-19?",
    "How does LLaVA handle multiple interleaved images?",
    "When is Christmas?",  # calendar.pdf
]


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
