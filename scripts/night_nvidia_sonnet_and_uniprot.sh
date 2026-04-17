#!/bin/bash
# Overnight: NVIDIA Sonnet comparison + UniProt Opus baseline
# Estimated: ~8 hours, ~$40-70
#
# Prerequisites:
#   - experiments/nvidia_gpu_1990_2024/M+/repeat_01/knowledge (NVIDIA Opus done)
#
# Steps:
#   1. NVIDIA Sonnet cold (6 runs, ~3h) — weak agent independent
#   2. NVIDIA Sonnet seeded (6 runs, ~3h) — weak agent + Opus knowledge
#   3. UniProt Opus (6 runs, ~2h) — baseline for next task

cd "$(dirname "$0")/.."
export PYTHONUNBUFFERED=1

TS=$(date +%Y%m%d_%H%M%S)
LOG_DIR="logs/overnight/night_${TS}"
mkdir -p "$LOG_DIR"

echo "============================================================"
echo "Overnight experiments — $(date)"
echo "Logs: $LOG_DIR"
echo "============================================================"

# -------- Helpers --------

run_step() {
  local name="$1"; shift
  local log="$LOG_DIR/${name}.log"
  echo ""
  echo "[$(date +%H:%M:%S)] >>> $name"
  echo "  Log: $log"
  if "$@" > "$log" 2>&1; then
    echo "[$(date +%H:%M:%S)] <<< $name COMPLETED"
  else
    echo "[$(date +%H:%M:%S)] <<< $name FAILED (exit $?) — continuing"
  fi
}

# -------- Pre-flight --------

echo ""
echo "Pre-flight checks:"

check_file() {
  if [ -f "$1" ]; then
    echo "  ✓ $1"
  else
    echo "  ✗ MISSING: $1"
    return 1
  fi
}

check_dir() {
  if [ -d "$1" ]; then
    echo "  ✓ $1"
  else
    echo "  ✗ MISSING: $1"
    return 1
  fi
}

missing=0
check_file tasks/nvidia_gpu_sonnet_cold.yaml   || missing=1
check_file tasks/nvidia_gpu_sonnet_seeded.yaml || missing=1
check_file tasks/uniprot_t2d.yaml              || missing=1
check_dir  experiments/nvidia_gpu_1990_2024/M+/repeat_01/knowledge || missing=1
check_file scripts/seed_and_run.sh             || missing=1

if [ "$missing" -eq 1 ]; then
  echo ""
  echo "ABORT: pre-flight failed."
  exit 1
fi

echo "  All pre-flight checks passed."

# -------- Step 1: NVIDIA Sonnet cold --------
# No dependency; weakest agent independently trying the task.

run_step "1_nvidia_sonnet_cold" \
  python -m forage learn tasks/nvidia_gpu_sonnet_cold.yaml \
    --num-runs 6 --group "M+" --repeat 1 --output experiments

# -------- Step 2: NVIDIA Sonnet seeded --------
# Seeds Sonnet's knowledge dir with Opus's repeat_01 knowledge,
# then runs full 6 runs accumulating on top.
#
# seed_and_run.sh handles: mkdir + cp + forage learn

run_step "2_nvidia_sonnet_seeded" \
  bash scripts/seed_and_run.sh \
    tasks/nvidia_gpu_sonnet_seeded.yaml 1 nvidia_gpu_1990_2024 1

# -------- Step 3: UniProt Opus baseline --------
# Fast (~2h); lays groundwork for UniProt Sonnet experiments later.

run_step "3_uniprot_opus" \
  python -m forage learn tasks/uniprot_t2d.yaml \
    --num-runs 6 --group "M+" --repeat 1 --output experiments

# -------- Step 4: UniProt Sonnet cold --------
# Sonnet independent; ~2-3h for UniProt's fast API task.

run_step "4_uniprot_sonnet_cold" \
  python -m forage learn tasks/uniprot_t2d_sonnet_cold.yaml \
    --num-runs 6 --group "M+" --repeat 1 --output experiments

# -------- Step 5: UniProt Sonnet seeded --------
# Seeds from Step 3's UniProt Opus knowledge, then runs.
# Depends on Step 3 completing.

run_step "5_uniprot_sonnet_seeded" \
  bash scripts/seed_and_run.sh \
    tasks/uniprot_t2d_sonnet_seeded.yaml 1 uniprot_t2d 1

echo ""
echo "============================================================"
echo "All steps attempted — $(date)"
echo "Check $LOG_DIR for individual logs."
echo "============================================================"
