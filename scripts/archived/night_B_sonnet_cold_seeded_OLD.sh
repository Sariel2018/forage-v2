#!/bin/bash
# Night B: Sonnet cold + seeded experiments (depends on Night A for Q10 knowledge)
# - NVIDIA Sonnet seeded
# - Q10 Sonnet cold
# - Q10 Sonnet seeded (needs Q10 Opus from Night A)
#
# Estimated: ~8-9 hours, ~$60-80
# Prerequisite: Night A must have completed Q10 Opus rerun

cd "$(dirname "$0")/.."
source scripts/overnight_phase1.sh

TS=$(date +%Y%m%d_%H%M%S)
LOG_DIR="logs/overnight/nightB_$TS"
mkdir -p "$LOG_DIR"

echo "============================================================"
echo "Night B: Sonnet cold + seeded — $(date)"
echo "Logs: $LOG_DIR"
echo "============================================================"

preflight_check \
  experiments/nvidia_gpu_1990_2024/M+/repeat_01/knowledge \
  experiments/first_proof_q10/M+/repeat_01/knowledge

# -----------------------------------------------------------
# Step 1: NVIDIA Sonnet seeded (from Opus repeat_01 knowledge)
# -----------------------------------------------------------
if seed_opus_knowledge "nvidia_gpu_1990_2024" "nvidia_gpu_1990_2024_sonnet"; then
  run_step "1_nvidia_sonnet_seeded" \
    python -m forage learn tasks/nvidia_gpu_sonnet.yaml \
      --num-runs 6 --group "M+" --repeat 2 --output experiments
fi

# -----------------------------------------------------------
# Step 2: Q10 Sonnet cold (new)
# -----------------------------------------------------------
run_step "2_q10_sonnet_cold" \
  python -m forage learn tasks/first_proof_q10_sonnet.yaml \
    --num-runs 6 --group "M+" --repeat 1 --output experiments

# -----------------------------------------------------------
# Step 3: Q10 Sonnet seeded (depends on Q10 Opus from Night A)
# -----------------------------------------------------------
if seed_opus_knowledge "first_proof_q10" "first_proof_q10_sonnet"; then
  run_step "3_q10_sonnet_seeded" \
    python -m forage learn tasks/first_proof_q10_sonnet.yaml \
      --num-runs 6 --group "M+" --repeat 2 --output experiments
fi

echo ""
echo "============================================================"
echo "Night B done — $(date)"
echo "============================================================"
