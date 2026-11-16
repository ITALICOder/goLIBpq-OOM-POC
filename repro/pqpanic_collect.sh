#!/bin/bash
cd /home/rasp/pqfix2/logs
for f in pqtest_main_auth_empty.log pqtest_main_auth_short.log pqtest_main_ps_nonull.log pqtest_main_qbool.log pqtest_main_qbin.log pqtest_main_cc_empty.log pqtest_main_rd_empty.log pqtest_main_err_nonull.log pqtest_main_rfq_empty.log pqtest_main_key_empty.log pqtest_main_neg_empty.log pqtest_main_ps_empty.log; do
  echo "### $f"
  grep -m3 -E "panic:|runtime error" "$f"
  grep -m2 -E "buf\.go|encode\.go|conn\.go|error\.go" "$f" | head -4
done
echo "### notif_empty (no handler)"
cat pqtest_main_notif_empty.log
echo "### cleartext"
cat pqtest_main_cleartext.log
