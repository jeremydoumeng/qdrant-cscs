#!/bin/bash
#SBATCH --job-name=qdrant-server
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --time=04:00:00
#SBATCH --output=logs/qdrant_%j.out
#SBATCH --error=logs/qdrant_%j.err
#SBATCH --account=a127

# Standalone Qdrant server on Alps GH200.
# Compile the binary first:  ./scripts/build_qdrant_alps.sh
# Then submit this sbatch; the server stays up until walltime ends or you scancel.

set -euo pipefail

# Under sbatch the script is copied to a spool dir, so BASH_SOURCE no longer
# points into the repo. Prefer SLURM_SUBMIT_DIR (the dir sbatch was run from);
# fall back to BASH_SOURCE for direct ./scripts/... execution.
REPO="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SCRATCH=${SCRATCH:-/iopsstor/scratch/cscs/$USER}
QDRANT_BIN=${QDRANT_BIN:-$REPO/qdrant-src/target/release/qdrant}
QDRANT_DATA=${QDRANT_DATA:-$SCRATCH/qdrant_server_${SLURM_JOB_ID:-local}}

[ -x "$QDRANT_BIN" ] || { echo "ERROR: $QDRANT_BIN not built. Run scripts/build_qdrant_alps.sh first." >&2; exit 1; }
mkdir -p logs "$QDRANT_DATA"

echo "node:    $SLURMD_NODENAME"
echo "binary:  $QDRANT_BIN"
echo "data:    $QDRANT_DATA"

QDRANT__SERVICE__HOST=127.0.0.1 \
QDRANT__SERVICE__MAX_WORKERS=4 \
QDRANT__STORAGE__STORAGE_PATH="$QDRANT_DATA" \
    exec "$QDRANT_BIN"
