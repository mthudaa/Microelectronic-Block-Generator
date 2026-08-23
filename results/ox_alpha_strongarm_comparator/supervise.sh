#!/bin/bash
# Bounded supervisor: resume the flow until tapeout-ready or 3 exhausted runs.
trap "" TERM
cd "$(dirname "$0")"
for i in 1 2 3; do
  echo "[SUPERVISOR] run $i start $(date)" >> flow.log
  nice -n 5 "$HOME/opensource-project/Microelectronic-Block-Generator/.venv/bin/python" -u run_flow.py >> flow.log 2>&1
  rc=$?
  echo "[SUPERVISOR] run $i exit=$rc $(date)" >> flow.log
  grep -q "TAPEOUT_READY: True" flow.log && break
done
echo "[SUPERVISOR] done $(date)" >> flow.log
