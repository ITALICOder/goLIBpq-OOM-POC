#!/bin/bash
# Panic battery: 16 crafted-message modes x 2 lib/pq versions.
# Crash = Go panic (exit 2, no recover in pq/database/sql) = vulnerability.
# Handled error = exit 0 with "ping:/query:" = NOT vulnerable for that mode.
cd /home/rasp/pqfix2
mkdir -p logs
SUM=logs/summary.txt
: > "$SUM"

STARTUP_MODES="auth_empty auth_short ps_empty ps_nonull rfq_empty key_empty notif_empty err_nonull neg_empty notice_empty"
POST_MODES="cc_empty rd_empty qbool qbin ok"
SPECIAL_MODES="cleartext"

start_srv() {
  pkill -f "panic_server[.]py" 2>/dev/null || true
  sleep 0.5
  setsid nohup python3 panic_server.py "$1" 5433 > "logs/srv_$1.out" 2>&1 < /dev/null &
  sleep 0.7
}

run_one() {
  local client=$1 mode=$2 cmode=$3
  start_srv "$mode"
  local out rc verdict
  out=$("./$client" "$cmode" 5433 Secret123 2>&1)
  rc=$?
  echo "$out" > "logs/${client#./}_${mode}.log"
  if [ $rc -eq 2 ] && echo "$out" | grep -q "panic:"; then
    verdict="CRASH(panic)"
  elif [ $rc -ne 0 ]; then
    verdict="exit=$rc other"
  elif echo "$out" | grep -qE "PING_OK|QUERY_DONE"; then
    verdict="no-crash (success)"
  else
    verdict="clean error (handled)"
  fi
  printf '%-16s %-16s %-16s %s\n' "${client#./}" "$mode" "$cmode" "$verdict" >> "$SUM"
}

for CLIENT in pqtest_v1123 pqtest_main; do
  for M in $STARTUP_MODES; do run_one "$CLIENT" "$M" ping; done
  for M in $POST_MODES; do run_one "$CLIENT" "$M" query; done
  for M in $SPECIAL_MODES; do run_one "$CLIENT" "$M" ping; done
done

pkill -f "panic_server[.]py" 2>/dev/null || true
echo "=== SUMMARY ==="
cat "$SUM"
echo "=== STOLEN CREDS (cleartext harvest) ==="
cat stolen_credentials.txt 2>/dev/null || echo "(none)"
echo "BATTERY_DONE"
