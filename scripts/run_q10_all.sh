#!/bin/bash
# Q10 Math Experiments: Opus baseline → Sonnet cold → Sonnet seeded
#
# Task: First Proof Q10 (Kolda) — PCG solver for RKHS-constrained CP tensor decomposition
# Model versions: claude-opus-4-6 / claude-sonnet-4-6 (pinned in yaml)
# Effort: high, max_turns: 50, max_rounds: 8
#
# Dependencies:
#   Step 1: none
#   Step 2: none (independent — weak agent without knowledge)
#   Step 3: depends on Step 1 (seeds Sonnet with Opus knowledge)
#
# Estimated: ~18-24h total (math tasks are slower — high effort + 50 turns)
#   Step 1: Opus 6 runs ~8-12h
#   Step 2: Sonnet cold 6 runs ~6-8h
#   Step 3: Sonnet seeded 6 runs ~6-8h

cd "$(dirname "$0")/.."
export PYTHONUNBUFFERED=1

TS=$(date +%Y%m%d_%H%M%S)
LOG_DIR="logs/q10_experiments/q10_${TS}"
mkdir -p "$LOG_DIR"

echo "============================================================"
echo "Q10 Math Experiments — $(date)"
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

missing=0

check_file() {
  if [ -f "$1" ]; then
    echo "  ✓ $1"
  else
    echo "  ✗ MISSING: $1"
    missing=1
  fi
}

check_file tasks/first_proof_q10.yaml
check_file tasks/first_proof_q10_sonnet_cold.yaml
check_file tasks/first_proof_q10_sonnet_seeded.yaml
check_file scripts/seed_and_run.sh

# Verify model versions are pinned (not short names)
echo ""
echo "Model version checks:"
for f in tasks/first_proof_q10.yaml tasks/first_proof_q10_sonnet_cold.yaml tasks/first_proof_q10_sonnet_seeded.yaml; do
  model=$(grep 'model:' "$f" | head -1 | awk '{print $2}' | tr -d '"')
  if [[ "$model" == "opus" || "$model" == "sonnet" ]]; then
    echo "  ✗ $f uses short name '$model' — must be pinned to full version"
    missing=1
  else
    echo "  ✓ $f → $model"
  fi
done

# Verify effort and max_turns
echo ""
echo "Parameter checks:"
for f in tasks/first_proof_q10.yaml tasks/first_proof_q10_sonnet_cold.yaml tasks/first_proof_q10_sonnet_seeded.yaml; do
  effort=$(grep 'effort:' "$f" | head -1 | awk '{print $2}' | tr -d '"')
  turns=$(grep 'max_turns_per_agent:' "$f" | head -1 | awk '{print $2}')
  echo "  $(basename $f): effort=$effort, max_turns=$turns"
done

if [ "$missing" -eq 1 ]; then
  echo ""
  echo "ABORT: pre-flight failed."
  exit 1
fi

echo ""
echo "  All pre-flight checks passed."

# -------- Step 1: Q10 Opus baseline --------
# No dependency; strong agent baseline for math task.

run_step "1_q10_opus" \
  python -m forage learn tasks/first_proof_q10.yaml \
    --num-runs 6 --group "M+" --repeat 1 --output experiments

# -------- Step 2: Q10 Sonnet cold --------
# No dependency on Step 1; weak agent independently trying math.
# Can run even if Step 1 fails.

run_step "2_q10_sonnet_cold" \
  python -m forage learn tasks/first_proof_q10_sonnet_cold.yaml \
    --num-runs 6 --group "M+" --repeat 1 --output experiments

# -------- Step 3: Q10 Sonnet seeded --------
# Depends on Step 1: seeds Sonnet's knowledge dir with Opus's repeat_01 knowledge.
# seed_and_run.sh handles: mkdir + cp + forage learn

run_step "3_q10_sonnet_seeded" \
  bash scripts/seed_and_run.sh \
    tasks/first_proof_q10_sonnet_seeded.yaml 1 first_proof_q10 1

echo ""
echo "============================================================"
echo "All Q10 steps attempted — $(date)"
echo "Check $LOG_DIR for individual logs."
echo "============================================================"
