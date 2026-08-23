#!/bin/bash
trap '' TERM
cd "$(dirname "$0")"
PY="$HOME/opensource-project/Microelectronic-Block-Generator/.venv/bin/python"
for i in $(seq 1 60); do
  echo "[LOOP] step $i start $(date +%H:%M:%S)" >> step.log
  "$PY" -u pex_step.py >> step.log 2>&1
  rc=$?
  echo "[LOOP] step $i exit=$rc" >> step.log
  [ $rc -ne 0 ] && break
  "$PY" -c "import json,sys; d=json.load(open('pex_state.json')); sys.exit(0 if d.get('done') else 1)" && break
done
echo "[LOOP] finished $(date)" >> step.log
