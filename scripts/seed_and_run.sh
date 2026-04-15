#!/bin/bash
# Helper: seed a Sonnet seeded task's knowledge dir from an Opus source, then run.
#
# Usage:
#   bash scripts/seed_and_run.sh <sonnet_task_yaml> <repeat> <opus_task_name> <opus_repeat>
#
# Example (UniProt seeded from Opus repeat_01, Sonnet as repeat_01):
#   bash scripts/seed_and_run.sh tasks/uniprot_t2d_sonnet_seeded.yaml 1 uniprot_t2d 1
#
# Example (UniProt seeded_deep from Opus repeat_02, Sonnet as repeat_01):
#   bash scripts/seed_and_run.sh tasks/uniprot_t2d_sonnet_seeded_deep.yaml 1 uniprot_t2d 2

set -e
cd "$(dirname "$0")/.."

SONNET_YAML="${1:?Usage: seed_and_run.sh <sonnet_yaml> <sonnet_repeat> <opus_task_name> <opus_repeat>}"
SONNET_REPEAT="${2:?Missing Sonnet repeat number}"
OPUS_TASK="${3:?Missing Opus task name}"
OPUS_REPEAT="${4:?Missing Opus repeat number}"

# Extract Sonnet task name from yaml
SONNET_TASK=$(grep "^  name:" "$SONNET_YAML" | head -1 | awk '{print $2}' | tr -d '"')

SRC="experiments/${OPUS_TASK}/M+/repeat_$(printf '%02d' $OPUS_REPEAT)/knowledge"
DEST="experiments/${SONNET_TASK}/M+/repeat_$(printf '%02d' $SONNET_REPEAT)/knowledge"

echo "Sonnet task:    $SONNET_TASK (repeat $SONNET_REPEAT)"
echo "Opus source:    $OPUS_TASK (repeat $OPUS_REPEAT)"
echo "Seed src:       $SRC"
echo "Seed dest:      $DEST"

if [ ! -d "$SRC" ]; then
  echo "ERROR: Opus source knowledge missing: $SRC"
  echo "Run Opus task first: python -m forage learn tasks/${OPUS_TASK}.yaml --num-runs 6 --group M+ --repeat $OPUS_REPEAT"
  exit 1
fi

echo ""
echo "Seeding knowledge..."
mkdir -p "$DEST"
cp -r "$SRC/." "$DEST/"

echo "Starting Sonnet seeded run..."
python -m forage learn "$SONNET_YAML" \
  --num-runs 6 --group "M+" --repeat "$SONNET_REPEAT" --output experiments
