#!/bin/bash
# Night A: Opus baselines (no dependencies on other experiments)
# - Q10 Opus rerun (archived due to isolation breach)
# - Q6 Opus new
# - UniProt Sonnet cold rerun (archived due to isolation breach)
# - UniProt Sonnet seeded_deep (new, seed from Opus repeat_02 knowledge)
#
# Estimated: ~10 hours, ~$60-90
# All independent — safe to run overnight in any order

cd "$(dirname "$0")/.."
source scripts/overnight_phase1.sh

TS=$(date +%Y%m%d_%H%M%S)
LOG_DIR="logs/overnight/nightA_$TS"
mkdir -p "$LOG_DIR"

echo "============================================================"
echo "Night A: Opus baselines + UniProt Sonnet reruns — $(date)"
echo "Logs: $LOG_DIR"
echo "============================================================"

preflight_check \
  experiments/uniprot_t2d/M+/repeat_02/knowledge

# -----------------------------------------------------------
# Step 1: UniProt Sonnet cold rerun (was archived)
# -----------------------------------------------------------
run_step "1_uniprot_sonnet_cold_rerun" \
  python -m forage learn tasks/uniprot_t2d_sonnet.yaml \
    --num-runs 6 --group "M+" --repeat 1 --output experiments

# -----------------------------------------------------------
# Step 2: UniProt Sonnet seeded_deep (from Opus repeat_02 knowledge)
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
  fi
fi

# -----------------------------------------------------------
# Step 3: Q10 Opus rerun (was archived — with new physical isolation)
# -----------------------------------------------------------
run_step "3_q10_opus_rerun" \
  python -m forage learn tasks/first_proof_q10.yaml \
    --num-runs 6 --group "M+" --repeat 1 --output experiments

# -----------------------------------------------------------
# Step 4: Q6 Opus baseline (new — needed for Q6 Sonnet seeded later)
# -----------------------------------------------------------
run_step "4_q6_opus_baseline" \
  python -m forage learn tasks/first_proof_q6.yaml \
    --num-runs 6 --group "M+" --repeat 1 --output experiments

echo ""
echo "============================================================"
echo "Night A done — $(date)"
echo "============================================================"
