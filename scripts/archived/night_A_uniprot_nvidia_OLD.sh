#!/bin/bash
# Night A: Complete UniProt + NVIDIA Sonnet experiments
# - UniProt Sonnet cold rerun (was archived due to isolation breach)
# - UniProt Sonnet seeded_deep (new — from Opus repeat_02 knowledge)
# - NVIDIA Sonnet seeded (new — from Opus repeat_01 knowledge)
#
# Q10 and Q6 left for later (require Opus baselines first).
#
# Estimated: ~8 hours, ~$50-70

cd "$(dirname "$0")/.."
source scripts/overnight_phase1.sh

TS=$(date +%Y%m%d_%H%M%S)
LOG_DIR="logs/overnight/nightA_$TS"
mkdir -p "$LOG_DIR"

echo "============================================================"
echo "Night A: Complete UniProt + NVIDIA Sonnet — $(date)"
echo "Logs: $LOG_DIR"
echo "============================================================"

preflight_check \
  experiments/uniprot_t2d/M+/repeat_01/knowledge \
  experiments/uniprot_t2d/M+/repeat_02/knowledge \
  experiments/nvidia_gpu_1990_2024/M+/repeat_01/knowledge

# -----------------------------------------------------------
# Step 1: UniProt Sonnet cold rerun (was archived)
# -----------------------------------------------------------
run_step "1_uniprot_sonnet_cold_rerun" \
  python -m forage learn tasks/uniprot_t2d_sonnet.yaml \
    --num-runs 6 --group "M+" --repeat 1 --output experiments

# -----------------------------------------------------------
# Step 2: UniProt Sonnet seeded_deep (Opus repeat_02 knowledge — found denom 218)
# -----------------------------------------------------------
seed_src="experiments/uniprot_t2d/M+/repeat_02/knowledge"
seed_dest="experiments/uniprot_t2d_sonnet/M+/repeat_03/knowledge"
if [ -d "$seed_src" ]; then
  mkdir -p "$seed_dest"
  if cp -r "$seed_src/." "$seed_dest/"; then
    echo "  Seeded: uniprot_t2d repeat_02 -> uniprot_t2d_sonnet repeat_03 (deep)"
    run_step "2_uniprot_sonnet_seeded_deep" \
      python -m forage learn tasks/uniprot_t2d_sonnet.yaml \
        --num-runs 6 --group "M+" --repeat 3 --output experiments
  else
    echo "[$(date +%H:%M:%S)] SKIPPED 2 (seed cp failed)"
  fi
else
  echo "[$(date +%H:%M:%S)] SKIPPED 2 (source missing)"
fi

# -----------------------------------------------------------
# Step 3: NVIDIA Sonnet seeded (Opus repeat_01 knowledge)
# -----------------------------------------------------------
if seed_opus_knowledge "nvidia_gpu_1990_2024" "nvidia_gpu_1990_2024_sonnet"; then
  run_step "3_nvidia_sonnet_seeded" \
    python -m forage learn tasks/nvidia_gpu_sonnet.yaml \
      --num-runs 6 --group "M+" --repeat 2 --output experiments
fi

echo ""
echo "============================================================"
echo "Night A done — $(date)"
echo "After: UniProt + NVIDIA experiments fully complete."
echo "Q10 + Q6 still pending (separate nights)."
echo "============================================================"
