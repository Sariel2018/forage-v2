#!/bin/bash
# Night 1: UniProt + NVIDIA Sonnet experiments (cold + Opus-seeded)
# Estimated: ~8 hours, ~$50-70

cd "$(dirname "$0")/.."
source scripts/overnight_phase1.sh

TS=$(date +%Y%m%d_%H%M%S)
LOG_DIR="logs/overnight/night1_$TS"
mkdir -p "$LOG_DIR"

echo "============================================================"
echo "Night 1: UniProt + NVIDIA Sonnet — $(date)"
echo "Logs: $LOG_DIR"
echo "============================================================"

# Pre-flight: verify Opus knowledge exists for seeding
preflight_check \
  experiments/uniprot_t2d/M+/repeat_01/knowledge \
  experiments/nvidia_gpu_1990_2024/M+/repeat_01/knowledge

# -----------------------------------------------------------
# UniProt Sonnet — cold start (repeat_01)
# -----------------------------------------------------------
run_step "1_uniprot_sonnet_cold" \
  python -m forage learn tasks/uniprot_t2d_sonnet.yaml \
    --num-runs 6 --group "M+" --repeat 1 --output experiments

# -----------------------------------------------------------
# UniProt Sonnet — Opus-seeded (repeat_02)
# -----------------------------------------------------------
if seed_opus_knowledge "uniprot_t2d" "uniprot_t2d_sonnet"; then
  run_step "2_uniprot_sonnet_opus_seeded" \
    python -m forage learn tasks/uniprot_t2d_sonnet.yaml \
      --num-runs 6 --group "M+" --repeat 2 --output experiments
else
  echo "[$(date +%H:%M:%S)] SKIPPED 2_uniprot_sonnet_opus_seeded (seed failed)"
fi

# -----------------------------------------------------------
# NVIDIA Sonnet — cold start (repeat_01)
# -----------------------------------------------------------
run_step "3_nvidia_sonnet_cold" \
  python -m forage learn tasks/nvidia_gpu_sonnet.yaml \
    --num-runs 6 --group "M+" --repeat 1 --output experiments

# -----------------------------------------------------------
# NVIDIA Sonnet — Opus-seeded (repeat_02)
# -----------------------------------------------------------
if seed_opus_knowledge "nvidia_gpu_1990_2024" "nvidia_gpu_1990_2024_sonnet"; then
  run_step "4_nvidia_sonnet_opus_seeded" \
    python -m forage learn tasks/nvidia_gpu_sonnet.yaml \
      --num-runs 6 --group "M+" --repeat 2 --output experiments
else
  echo "[$(date +%H:%M:%S)] SKIPPED 4_nvidia_sonnet_opus_seeded (seed failed)"
fi

# -----------------------------------------------------------
# UniProt Sonnet — seeded with Opus repeat_02 knowledge (repeat_03)
# Tests whether deeper Opus knowledge (repeat_02 found denom 218) transfers
# more effectively than shallow Opus knowledge (repeat_01 found denom ~30)
# -----------------------------------------------------------
seed_src="experiments/uniprot_t2d/M+/repeat_02/knowledge"
seed_dest="experiments/uniprot_t2d_sonnet/M+/repeat_03/knowledge"
if [ -d "$seed_src" ]; then
  mkdir -p "$seed_dest"
  if cp -r "$seed_src/." "$seed_dest/"; then
    echo "  Seeded: uniprot_t2d repeat_02 -> uniprot_t2d_sonnet repeat_03 (deep knowledge)"
    run_step "5_uniprot_sonnet_opus_repeat02_seeded" \
      python -m forage learn tasks/uniprot_t2d_sonnet.yaml \
        --num-runs 6 --group "M+" --repeat 3 --output experiments
  else
    echo "[$(date +%H:%M:%S)] SKIPPED 5_uniprot_sonnet_opus_repeat02_seeded (cp failed)"
  fi
else
  echo "[$(date +%H:%M:%S)] SKIPPED 5_uniprot_sonnet_opus_repeat02_seeded (source missing: $seed_src)"
fi

echo ""
echo "============================================================"
echo "Night 1 done — $(date)"
echo "============================================================"
