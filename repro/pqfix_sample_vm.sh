#!/bin/bash
# Samples VmPeak (high-water virtual memory) of a pid until it dies.
# usage: sample_vm.sh <pid> <outfile>
PID=$1
OUT=$2
MAX=0
while kill -0 "$PID" 2>/dev/null; do
  V=$(awk '/VmPeak/{print $2}' "/proc/$PID/status" 2>/dev/null)
  [ -z "$V" ] && V=0
  [ "$V" -gt "$MAX" ] && MAX=$V
  sleep 0.3
done
echo "VmPeak_max_kB=$MAX" > "$OUT"
echo "VmPeak_max_kB=$MAX"
