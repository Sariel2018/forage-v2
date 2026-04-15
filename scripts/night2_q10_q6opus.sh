#!/bin/bash
# Night 2: Q10 Sonnet (both variants) + Q6 Opus baseline
# Q6 Opus runs last so next night's Q6 Sonnet seeded has knowledge to inherit
# Estimated: ~9 hours, ~$60-80

cd "$(dirname "$0")/.."
source scripts/overnight_phase1.sh

TS=$(date +%Y%m%d_%H%M%S)
LOG_DIR="logs/overnight/night2_$TS"
mkdir -p "$LOG_DIR"

echo "============================================================"
echo "Night 2: Q10 Sonnet + Q6 Opus — $(date)"
echo "Logs: $LOG_DIR"
echo "============================================================"

# Pre-flight: Q10 Opus knowledge needed for seeding Q10 Sonnet
preflight_check experiments/first_proof_q10/M+/repeat_01/knowledge

# -----------------------------------------------------------
# Q10 Sonnet — cold start (repeat_01)
# -----------------------------------------------------------
run_step "1_q10_sonnet_cold" \
  python -m forage learn tasks/first_proof_q10_sonnet.yaml \
    --num-runs 6 --group "M+" --repeat 1 --output experiments

# -----------------------------------------------------------
# Q10 Sonnet — Opus-seeded (repeat_02)
# -----------------------------------------------------------
if seed_opus_knowledge "first_proof_q10" "first_proof_q10_sonnet"; then
  run_step "2_q10_sonnet_opus_seeded" \
    python -m forage learn tasks/first_proof_q10_sonnet.yaml \
      --num-runs 6 --group "M+" --repeat 2 --output experiments
else
  echo "[$(date +%H:%M:%S)] SKIPPED 2_q10_sonnet_opus_seeded (seed failed)"
fi

# -----------------------------------------------------------
# Q6 Opus M+ baseline — needed before Q6 Sonnet seeded can run (Night 3)
# -----------------------------------------------------------
run_step "3_q6_opus_baseline" \
  python -m forage learn tasks/first_proof_q6.yaml \
    --num-runs 6 --group "M+" --repeat 1 --output experiments

echo ""
echo "============================================================"
echo "Night 2 done — $(date)"
echo "============================================================"
