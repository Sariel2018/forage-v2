#!/bin/bash
# Forage v2 Phase 1 — Common helpers for overnight experiments
# Source this file from night-specific scripts
#
# Three conditions per task (Opus already done, Sonnet to run):
#   1. Opus M+ (ceiling baseline)
#   2. Sonnet M+ cold start (repeat_01) — self-learning from scratch
#   3. Sonnet M+ Opus-seeded (repeat_02) — inherits Opus's knowledge, continues learning
#
# Core question: does Sonnet with Opus knowledge catch up to Opus?

cd "$(dirname "$0")/.."
export PYTHONUNBUFFERED=1

run_step() {
  local name=$1
  shift
  local log="$LOG_DIR/${name}.log"
  echo ""
  echo "[$(date +%H:%M:%S)] >>> $name"
  echo "  Log: $log"
  if "$@" > "$log" 2>&1; then
    echo "[$(date +%H:%M:%S)] <<< $name COMPLETED"
  else
    echo "[$(date +%H:%M:%S)] <<< $name FAILED (continuing to next step)"
  fi
}

seed_opus_knowledge() {
  # Copy Opus accumulated knowledge to Sonnet's M+/repeat_02 directory.
  # learning_curve.py sees existing knowledge dir and uses it as initial state.
  # Returns non-zero if source missing or copy fails — caller must check.
  local opus_task=$1
  local sonnet_task=$2
  local src="experiments/${opus_task}/M+/repeat_01/knowledge"
  local dest="experiments/${sonnet_task}/M+/repeat_02/knowledge"

  if [ ! -d "$src" ]; then
    echo "  SEED FAILED: source missing: $src"
    return 1
  fi

  mkdir -p "$dest"
  if ! cp -r "$src/." "$dest/"; then
    echo "  SEED FAILED: cp error from $src to $dest"
    return 1
  fi

  echo "  Seeded: $opus_task -> $sonnet_task (repeat_02)"
  return 0
}

preflight_check() {
  # Verify Opus knowledge directories exist before burning hours on runs.
  local missing=0
  for p in "$@"; do
    if [ ! -d "$p" ]; then
      echo "  MISSING Opus knowledge: $p"
      missing=1
    fi
  done
  if [ "$missing" -eq 1 ]; then
    echo "Pre-flight FAILED. Aborting."
    exit 1
  fi
  echo "  Pre-flight OK: all Opus knowledge dirs present."
}
