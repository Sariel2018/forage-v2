#!/bin/bash
# Night 3: Q6 Sonnet (cold + Opus-seeded)
# Requires Night 2 to have completed Q6 Opus M+ baseline
# Estimated: ~6 hours, ~$40-60

cd "$(dirname "$0")/.."
source scripts/overnight_phase1.sh

TS=$(date +%Y%m%d_%H%M%S)
LOG_DIR="logs/overnight/night3_$TS"
mkdir -p "$LOG_DIR"

echo "============================================================"
echo "Night 3: Q6 Sonnet — $(date)"
echo "Logs: $LOG_DIR"
echo "============================================================"

# Pre-flight: Q6 Opus knowledge must exist (from Night 2)
preflight_check experiments/first_proof_q6/M+/repeat_01/knowledge

# -----------------------------------------------------------
# Q6 Sonnet — cold start (repeat_01)
# -----------------------------------------------------------
run_step "1_q6_sonnet_cold" \
  python -m forage learn tasks/first_proof_q6_sonnet.yaml \
    --num-runs 6 --group "M+" --repeat 1 --output experiments

# -----------------------------------------------------------
# Q6 Sonnet — Opus-seeded (repeat_02)
# -----------------------------------------------------------
if seed_opus_knowledge "first_proof_q6" "first_proof_q6_sonnet"; then
  run_step "2_q6_sonnet_opus_seeded" \
    python -m forage learn tasks/first_proof_q6_sonnet.yaml \
      --num-runs 6 --group "M+" --repeat 2 --output experiments
else
  echo "[$(date +%H:%M:%S)] SKIPPED 2_q6_sonnet_opus_seeded (seed failed)"
fi

echo ""
echo "============================================================"
echo "Night 3 done — $(date)"
echo "============================================================"
