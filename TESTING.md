# Testing on Alps — session resume

Copy-pasteable checklist for re-running the smoke tests on Alps after
an `ssh` reconnect. Assumes the repo is already cloned and the binary
already built (i.e. you ran the README's steps 1-2 in a previous
session). If not, do those first.

## 0. Set scope

```bash
export REPO=$SCRATCH/qdrant-cscs            # wherever you cloned
export QDRANT_BIN=$REPO/qdrant-src/target/release/qdrant
cd $REPO
```

Sanity:

```bash
[ -x "$QDRANT_BIN" ] && echo "binary OK" || echo "rebuild needed: ./scripts/build_qdrant_alps.sh"
$QDRANT_BIN --version
```

## 1. Allocate a node + start the server (one job)

```bash
sbatch scripts/start_qdrant_server.sbatch
squeue -u $USER -n qdrant-server -o "%i %T %M %L %R"   # wait for RUNNING
```

When `RUNNING`, capture the node:

```bash
QDRANT_NODE=$(squeue -u $USER -n qdrant-server -h -o "%R")
echo "server on: $QDRANT_NODE"
```

## 2. From a separate shell on the same node — verify

The server binds to `127.0.0.1:6333` on `$QDRANT_NODE`. Easiest is
to `srun` a quick check on that node:

```bash
srun --jobid=<JOBID> --overlap curl -fsS http://127.0.0.1:6333/healthz
# → "healthz check passed"

srun --jobid=<JOBID> --overlap curl -fsS http://127.0.0.1:6333/collections
# → {"result":{"collections":[]},...}
```

## 3. Run the smoke tests

All three need `mmore` importable. Pick a `MMORE_SRC`:

```bash
export MMORE_SRC=/path/to/your/mmore/src         # or any clone with the qdrant backend
export PYTHONPATH=$MMORE_SRC:${PYTHONPATH:-}
```

Each test in a separate `srun --overlap` on the server's node:

```bash
srun --jobid=<JOBID> --overlap python tests/test_qdrant_server.py
srun --jobid=<JOBID> --overlap python tests/test_qdrant_colpali.py
srun --jobid=<JOBID> --overlap python tests/test_colpali_real.py
```

Expected exit codes: 0 for each. Each prints a final `PASSED` line.

## 4. Inspect / persist

```bash
# point at the persistent storage path (default: $SCRATCH/qdrant_server_<JOBID>/)
ls $SCRATCH/qdrant_server_*/

# server logs
tail -F logs/qdrant_<JOBID>.{out,err}

# what collections you created
srun --jobid=<JOBID> --overlap curl -s http://127.0.0.1:6333/collections | python -m json.tool
```

## 5. Cleanup

```bash
scancel <JOBID>                          # stop the server
rm -rf $SCRATCH/qdrant_server_<JOBID>    # if you don't want the index to survive
```

## Troubleshooting

| symptom | fix |
|---|---|
| `Unsupported system page size` | binary wasn't built with `JEMALLOC_SYS_WITH_LG_PAGE=16`. Rerun `./scripts/build_qdrant_alps.sh`. |
| `connection refused` from curl | server hasn't bound yet (give it 5 s after RUNNING) or you're on the wrong node — use `srun --overlap`. |
| `ImportError: mmore.colpali` | `$MMORE_SRC` not on `PYTHONPATH`. Re-export. |
| `qdrant-src/target/release/qdrant: No such file` | binary not built. Run `./scripts/build_qdrant_alps.sh`. |
