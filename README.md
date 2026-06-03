# mmore Qdrant benchmark scratch — Alps

This directory contains the bench setup for running **mmore** with a real
Qdrant **server** (not the embedded local mode) on CSCS Alps GH200 nodes.

It exists to support the MIRIAD-5.8M benchmark, where embedded-mode Qdrant
is too slow at retrieval scale.

The directory is **separate from the open PR** ([swiss-ai/mmore#283](https://github.com/swiss-ai/mmore/pull/283))
so nothing here changes the code under review.

## Why we needed to do anything

The mmore PR adds a Qdrant adapter that can run in two modes:

- **Embedded** (`QdrantClient(path=...)`) — pure-Python, works anywhere,
  but slow at >1M points.
- **Server** (`QdrantClient(url="http://...")`) — Rust binary, fast, but
  requires a running `qdrant` process.

For MIRIAD-5.8M we need server mode. That ran into two upstream-packaging
problems on Alps:

| | Milvus | Qdrant |
|---|---|---|
| Symptom | No aarch64 wheel for `milvus-lite` | aarch64 binary aborts at startup |
| Root cause | Upstream only ships x86_64 | jemalloc compiled assuming 4KB pages |
| Fails at | install time | runtime (`<jemalloc>: Unsupported system page size`) |
| Embedded mode | Doesn't work (no wheel) | Works but slow |
| Server mode | Need the OSS Milvus server (heavy) | Need a Qdrant binary that handles 64KB pages |

The first is what the PR solves (drop in Qdrant adapter). The second is
what this directory solves (rebuild the Qdrant binary for the actual
system).

## Why the prebuilt binary doesn't work

CSCS Alps GH200 nodes use a **64KB kernel page size** (HPC tradeoff:
fewer TLB misses on huge working sets). Most aarch64 systems —
Apple Silicon, AWS Graviton, Raspberry Pi — use 4KB pages.

Qdrant's prebuilt aarch64 binary statically links jemalloc compiled
against 4KB pages. jemalloc detects the mismatch at startup and aborts:

```
<jemalloc>: Unsupported system page size
<jemalloc>: Unsupported system page size
terminate called without an active exception
```

The 6.5 GB `core_nid006261_*` files you may see in the user's home are
core dumps from this exact crash on compute nodes.

## The fix

Build Qdrant from source on this system. The crate `tikv-jemalloc-sys`
honors a build-time env var that recompiles jemalloc itself:

```
JEMALLOC_SYS_WITH_LG_PAGE=16   # 16 = log2(65536)
```

No code changes — same Qdrant source as upstream, just compiled with the
right page size assumption.

## What's in here

```
bench/
├── README.md                      # this file
├── build_qdrant_alps.sh           # one-command rebuild recipe (see below)
├── test_qdrant_server.py          # server-mode smoke test (5 docs, 3 queries)
├── qdrant-src/                    # Qdrant v1.17.1 source tree (cloned)
│   └── target/release/qdrant      # 72 MB working binary  ← THE BUILT BINARY
├── qdrant-data/                   # server storage path (currently empty)
├── qdrant.log                     # last server run's stdout/stderr
├── protoc/bin/protoc              # protoc 34.1 aarch64 (build-time dep)
└── mmore-qdrant/                  # clone of jeremydoumeng/mmore-qdrant qdrant-backend
    ├── .venv/                     # Python 3.11 venv with mmore[qdrant,rag]
    └── ...                        # mirrors the PR layout exactly
```

## Reproducing the build from scratch

```bash
cd bench
./build_qdrant_alps.sh                # default: v1.17.1
./build_qdrant_alps.sh v1.18.0        # bump Qdrant version
```

Idempotent: skips rustup if `cargo` exists, skips protoc if already
unzipped, refuses to clobber an existing source tree at a different tag.
First clean run takes ~20 min; incremental rebuilds after Qdrant version
bumps are faster.

## Running the server

```bash
QDRANT__SERVICE__HOST=127.0.0.1 \
QDRANT__SERVICE__MAX_WORKERS=4 \
QDRANT__STORAGE__STORAGE_PATH=/abs/path/to/qdrant-data \
bench/qdrant-src/target/release/qdrant
```

Flags worth knowing:

- `QDRANT__SERVICE__HOST=127.0.0.1` — loopback only; otherwise binds
  `0.0.0.0` and is reachable from other users on the same login node.
- `QDRANT__SERVICE__MAX_WORKERS=4` — without this, qdrant spawns one
  actix worker per core (288 on a login node — overkill for a single
  client).
- `QDRANT__STORAGE__STORAGE_PATH=...` — required if you don't `cd` to a
  dir with a `./storage/` ready.

Health check: `curl http://127.0.0.1:6333/healthz` (200 OK in ~1s after
launch).

## Smoke-testing the full pipeline

The `mmore-qdrant/` clone has the PR's `test_qdrant_pipeline.py` which
runs against embedded mode. `bench/test_qdrant_server.py` is the
server-mode equivalent — same 5 docs, same 3 queries, but
`uri="http://127.0.0.1:6333"`:

```bash
# 1. Start the server (in another terminal or as a SLURM step)
bench/qdrant-src/target/release/qdrant &

# 2. Run the test
bench/mmore-qdrant/.venv/bin/python bench/test_qdrant_server.py
```

Expected output: `Server-mode smoke test PASSED.` Two of three queries
return their exact correct top-1; the "Obama" query returns Python
instead — this is the documented RRF-vs-WeightedRanker quirk and matches
embedded-mode behavior.

## Consequences of the workaround

- **Binary is Alps-specific.** Won't run on 4KB-page systems (laptops,
  most cloud VMs, Apple Silicon, default Graviton). It runs on any other
  Alps node with the same OS image (same glibc, same 64KB pages).
- **Client side: no impact.** `qdrant-client` (Python) and the PR's
  `QdrantMilvusClient` adapter are unchanged. Embedded mode still works
  on any architecture.
- **Future Qdrant upgrades** require running the build script again with
  the new tag. Captured in `build_qdrant_alps.sh` so this is one
  command, not tribal knowledge.
- **Reproducibility.** Pinned: Qdrant `v1.17.1`, Rust 1.95.0, protoc
  34.1, `JEMALLOC_SYS_WITH_LG_PAGE=16`, `Cargo.lock` from the tag.
- **Footprint.** ~3 GB build artifacts in `qdrant-src/target/`,
  ~1.2 GB Rust toolchain in `~/.cargo` + `~/.rustup`, 72 MB final
  binary. To distribute the binary alone, copy it together with
  `qdrant-src/config/` (or set every `QDRANT__*` env var explicitly).
- **The PR is untouched.** This entire directory could be deleted and
  the PR is unaffected.

## What's verified to work

1. Qdrant 1.17.1 server starts cleanly on a 64KB-page Alps node, no
   jemalloc abort.
2. HTTP API (`/healthz`, `/collections`) responds correctly.
3. Python `qdrant-client>=1.10` (the PR's pin) talks to server v1.17 —
   no protocol mismatch.
4. The PR's `QdrantMilvusClient` adapter switches to server mode on an
   `http://` URI and runs the full mmore Indexer + Retriever flow
   end-to-end. Hybrid search returns plausible top-k.

## Pending

- Capture build recipe in a script — **done** (`build_qdrant_alps.sh`).
- Set up MIRIAD subsample + SLURM job for the actual benchmark.
- Decide whether to upstream the build script into the PR (`scripts/`
  directory) or keep it as a CSCS-internal asset.
