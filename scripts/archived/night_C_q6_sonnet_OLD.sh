#!/bin/bash
# Night C: Q6 Sonnet experiments (depends on Night A's Q6 Opus baseline)
# - Q6 Sonnet cold
# - Q6 Sonnet seeded
#
# Estimated: ~6 hours, ~$40-60
# Prerequisite: Night A must have completed Q6 Opus

cd "$(dirname "$0")/.."
source scripts/overnight_phase1.sh

TS=$(date +%Y%m%d_%H%M%S)
LOG_DIR="logs/overnight/nightC_$TS"
mkdir -p "$LOG_DIR"

echo "============================================================"
echo "Night C: Q6 Sonnet — $(date)"
echo "Logs: $LOG_DIR"
echo "============================================================"

preflight_check experiments/first_proof_q6/M+/repeat_01/knowledge

# -----------------------------------------------------------
# Step 1: Q6 Sonnet cold
# -----------------------------------------------------------
run_step "1_q6_sonnet_cold" \
  python -m forage learn tasks/first_proof_q6_sonnet.yaml \
    --num-runs 6 --group "M+" --repeat 1 --output experiments

# -----------------------------------------------------------
# Step 2: Q6 Sonnet seeded
# -----------------------------------------------------------
if seed_opus_knowledge "first_proof_q6" "first_proof_q6_sonnet"; then
  run_step "2_q6_sonnet_seeded" \
    python -m forage learn tasks/first_proof_q6_sonnet.yaml \
      --num-runs 6 --group "M+" --repeat 2 --output experiments
fi

echo ""
echo "============================================================"
echo "Night C done — $(date)"
echo "============================================================"
