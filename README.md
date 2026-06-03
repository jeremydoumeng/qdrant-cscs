# qdrant-cscs

Run a [Qdrant](https://qdrant.tech) vector-search server on CSCS Alps
GH200 nodes. Prebuilt aarch64 Qdrant binaries crash at startup on Alps
(`<jemalloc>: Unsupported system page size`) because the bundled
jemalloc assumes 4 KB pages and Alps uses 64 KB pages. This repo
contains the build script that fixes that, a Slurm wrapper to launch
the server, and three smoke tests.

## Prerequisites

- CSCS Alps account with a Slurm allocation (e.g. `--account=a127`).
- Scratch space at `/iopsstor/scratch/cscs/$USER` (or set `SCRATCH=...`).
- Rust toolchain — the build script installs `rustup` automatically if it isn't on the PATH.
- Tests (steps 5-7) need [mmore](https://github.com/swiss-ai/mmore) installed and importable. Point `PYTHONPATH` or `MMORE_SRC` at your checkout.

## 1. Clone

```bash
cd $SCRATCH                          # or anywhere writable
git clone https://github.com/jeremydoumeng/qdrant-cscs.git
cd qdrant-cscs
```

## 2. Build the Qdrant binary (~5 min, one-time)

```bash
./scripts/build_qdrant_alps.sh              # default v1.17.1
./scripts/build_qdrant_alps.sh v1.18.0      # pin a different release
```

Sets `JEMALLOC_SYS_WITH_LG_PAGE=16` (= log₂(65536)) so jemalloc matches
the system page size. Output: `qdrant-src/target/release/qdrant`.

## 3. Start the server

Submit the standalone Slurm wrapper. It exec's the binary directly so
the Slurm allocation is the server lifecycle:

```bash
sbatch scripts/start_qdrant_server.sbatch
```

Defaults: `127.0.0.1:6333`, storage on `$SCRATCH/qdrant_server_<JOBID>`,
4 worker threads, 4h walltime. Override via env vars
(`QDRANT_DATA`, `QDRANT_BIN`) or sbatch flags.

## 4. Verify

From any node that can reach the server (typically the same node — the
server binds to localhost):

```bash
curl http://127.0.0.1:6333/healthz             # → "healthz check passed"
curl http://127.0.0.1:6333/collections         # → {"result":{"collections":[]}, ...}
```

## 5. Set up the test environment (one-time)

The smoke tests need [mmore](https://github.com/swiss-ai/mmore) plus several
deps the `[qdrant]` extra does not pull on its own (the indexer eagerly imports
mmore's LangChain provider stack; the ColPali test needs
`colpali-engine`/`pymupdf`/`pyarrow`). One script installs everything into a
venv:

```bash
scripts/setup_test_env.sh /path/to/mmore        # creates .venv, installs all deps
source .venv/bin/activate
export MMORE_SRC=/path/to/mmore/src
export PYTHONPATH=$MMORE_SRC
```

After this, the three test commands below run directly.

## 6. Smoke test: pure-Qdrant adapter against the server

```bash
python tests/test_qdrant_server.py
```

Indexes 5 toy documents, runs 3 retrievals, prints top-1 for each.

## 7. Smoke test: ColPali multi-vector / MaxSim correctness

```bash
python tests/test_qdrant_colpali.py
```

Synthetic 5-page corpus, validates `QdrantColpaliManager`'s late-interaction MaxSim against the expected top-1 ranking.

## 8. Smoke test: real-PDF retrieval

Needs a **GPU** (loads `vidore/colpali-v1.3`). Self-contained: if the
`colpali_real_pdf` collection is empty it first builds it from mmore's bundled
sample PDFs (COVID/LLaVA/calendar), then queries — so just run:

```bash
python tests/test_colpali_real.py
```

First run is slow (model download + corpus build); later runs reuse the
collection. COVID/LLaVA queries hit their source PDF strongly; the calendar
query is a weak match (that PDF is image-heavy with little matching text).

## File layout

```
qdrant-cscs/
├── README.md                        — this file
├── scripts/
│   ├── build_qdrant_alps.sh         — compile the Qdrant binary
│   ├── start_qdrant_server.sbatch   — Slurm wrapper to launch it
│   └── setup_test_env.sh            — venv + all test deps (one-time)
└── tests/
    ├── test_qdrant_server.py        — pure-Qdrant smoke (needs mmore)
    ├── test_qdrant_colpali.py       — ColPali MaxSim correctness (needs mmore)
    └── test_colpali_real.py         — real-PDF ColPali retrieval; auto-builds its corpus (GPU)
```

## Notes

- **Page size on Alps** — `getconf PAGESIZE` returns `65536` (64 KB).
  Standard aarch64 systems (Apple Silicon, Graviton, Raspberry Pi)
  return `4096`. jemalloc bakes the page size into its binary at
  build time, hence the rebuild.
- **Why a server at all** — embedded mode (`QdrantClient(path=...)`,
  pure Python) is fine up to ~5k chunks or ~2k ColPali pages. Above
  that the server's Rust hot path is essential.
- **Lifecycle** — the server is just a Slurm job. `scancel <JOBID>` to
  stop. The on-disk index at `$QDRANT_DATA` survives between sessions
  if you point new submissions at the same path.
