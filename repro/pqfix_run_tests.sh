#!/bin/bash
cd /home/rasp/pqfix
mkdir -p logs
: > evil.payloads

start_srv() {
  pkill -f "evil_pg[.]py" 2>/dev/null || true
  sleep 1
  setsid nohup python3 evil_pg.py "$1" 5433 30 > "logs/srv_$1.out" 2>&1 < /dev/null &
  sleep 1
}
stop_srv() {
  pkill -f "evil_pg[.]py" 2>/dev/null || true
  sleep 1
}

echo "=== R1: latest RELEASE v1.12.3 + HTTP reply (baseline: still vulnerable) ==="
start_srv http
./client1123_arm 5 5433 10 > logs/r1.log 2>&1
echo "R1 exit=$?"
grep -n -m6 -E "fatal error|out of memory|makeslice|lib/pq|lost synchron" logs/r1.log || tail -5 logs/r1.log

echo "=== R2: FIXED main + HTTP reply (their fix should hold here) ==="
start_srv http
./clientmain_arm 10 5433 10 > logs/r2.log 2>&1
echo "R2 exit=$?"
grep -n -m6 -E "fatal error|out of memory|makeslice|lost synchron|ALL_DONE" logs/r2.log || tail -5 logs/r2.log

echo "=== R3: FIXED main + DataRow 1GiB x100 conns (bypass of the fix) ==="
start_srv d1g
./clientmain_arm 100 5433 15 > logs/r3.log 2>&1
echo "R3 exit=$?"
grep -n -m8 -E "fatal error|out of memory|makeslice|lib/pq|ALL_DONE" logs/r3.log || tail -5 logs/r3.log

echo "=== R4: FIXED main 64-bit + DataRow 1GiB x100 (VmPeak proof) ==="
start_srv d1g
./clientmain_arm64 100 5433 15 > logs/r4.log 2>&1 &
CPID=$!
bash sample_vm.sh $CPID logs/r4_vm.txt
wait $CPID
echo "R4 exit=$?"
cat logs/r4_vm.txt
grep -n -m4 -E "fatal error|out of memory|ALL_DONE" logs/r4.log || tail -3 logs/r4.log

echo "=== R5: FIXED main 64-bit + streaming -> kernel OOM kill ==="
start_srv d1gstream
./clientmain_arm64 100 5433 20 > logs/r5.log 2>&1
echo "R5 exit=$?"
tail -3 logs/r5.log
sudo -n dmesg 2>/dev/null | tail -8 > logs/r5_dmesg.txt || true
cat logs/r5_dmesg.txt 2>/dev/null

stop_srv
echo "ALL_TESTS_DONE"
