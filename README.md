# goLIBpq-OOM-POC
Still after an attempt to fix the previous bug we found in fscan that was related to and older version "pre-fix" for go lib/pq, the patch actually didnt resolve anything at all,here the demostration:

**lib/pq's fix for issue 1(check the first test on fscan that was utilizing the "unpatched" version https://github.com/ITALICOder/OOM-POC-fscan/) is incomplete** — commit `b125f757` (main only, unreleased) caps message length at 30 KB *only for types not in `ValidLongMessageType`*. A hostile server switches one byte (`'H'` → `'D'` DataRow) and the allocation is uncapped again: measured **101.8 GB VmPeak** from 100 connections × 5-byte replies, plus a deterministic Go fatal on 32-bit and a kernel OOM kill on 64-bit. Latest **release v1.12.3 has no check at all**. Details: `ISSUE_3_pq-incomplete-fix.md`.

## Issue — lib/pq's fix (`b125f757`) is bypassable; concurrency defeats any per-message cap

Verified against `main` @ `45ac10e` (2026-08-20, includes the fix) and release **v1.12.3** (no check at all):

| # | pq version | Server reply | Result |
|---|---|---|---|
| R1 | v1.12.3 (latest release) | HTTP 403 page | 💥 exit 2, `makeslice(0x5454502b)` — release unfixed |
| R2 | main (fixed) | HTTP 403 page | ✅ rejected: `lost synchronization ... length 1414811691` |
| R3 | **main (fixed)** | **`'D'` + 1 GiB × 100 conns** | 💥 **exit 2**, `makeslice(0x40000000)` @ `conn.go:1131` — bypass |
| R4 | main (fixed) 64-bit | `'D'` + 1 GiB × 100 conns | **VmPeak = 106,697,936 kB ≈ 101.8 GB** |
| R5 | main (fixed) 64-bit | `'D'` + 1 GiB + stream | 💥 **exit 137, kernel OOM kill** (`total-vm:108460768kB`) |

The check `if !proto.ValidLongMessageType(t) && n > proto.MaxMsgLen` exempts `DataRow/RowDescription/Error/CopyData/FunctionCall/Notice/Notification` — the peer picks `'D'` and `make([]byte, n)` runs uncapped (full uint32 ≈ 4.29 GB). And even a correct 1 GB cap × 100 concurrent connections = 100 GB, as measured. Full writeup: `ISSUE_3_pq-incomplete-fix.md`; logs: `evidence/pqfix_r1..r5.log`, `pqfix_r5_dmesg.txt`, `pqfix_r4_vmpeak.txt`; repro: `repro/pqfix_*`.

# Analyzing fully the code for find others bug i encounter even a better panic generator described here(BufPanic4every2):

**lib/pq panics on malformed server messages — remote process kill with a single 5-byte message** — the `buf.go` parsers (`int32/int16/byte/next/string`) do unchecked slice ops on peer-supplied bytes and `string()` *explicitly panics*; no `recover()` exists anywhere in pq or `database/sql`. **12 of 16 crafted messages crash both v1.12.3 and main**, instantly and with zero memory pressure (the OOM issue needs RAM pressure; this doesn't). Details: `ISSUE_4_pq-remote-panic.md`.

## Issue 4 — remote panic DoS: malformed messages kill any client (5-byte messages, 12 variants)

32-run battery (16 modes × v1.12.3 + main): **12 modes crash both versions** with Go panics — `buf.go:16` (int32 on <4 bytes), `buf.go:29` (int16), `buf.go:37` (explicit "expected string terminator" panic on peer data), `buf.go:46` (byte/next), `encode.go:118` (bool `s[0]` on empty value), `encode.go:70` (binaryDecode `Uint64` on 2 bytes); `error.go:130` for malformed ErrorResponse. 2 more (`A`/`N` messages) crash as soon as an app registers notice/notification handlers. Control mode passes. **No `recover()` exists in pq or `database/sql` → panic = process death (exit 2).** Works instantly with zero memory pressure, on any RAM size — strictly easier than the OOM. Full matrix: `evidence/pqpanic_logs/summary.txt`; writeup: `ISSUE_4_pq-remote-panic.md`.

Also captured: hostile server requests `AuthenticationCleartextPassword` → client sends DSN password in the clear (`evidence/pqpanic_stolen_credentials.txt`) — protocol-by-design (libpq parity), but relevant to scanners that connect dictionary passwords to untrusted hosts.

## Files

```
README.md                             this document
ISSUE_1_remote-oom-crash.md           ready-to-file issue text (fscan)
ISSUE_2_socks5-bypass.md              ready-to-file issue text (fscan)
ISSUE_3_pq-incomplete-fix.md          ready-to-file issue text (lib/pq)
ISSUE_4_pq-remote-panic.md            ready-to-file issue text (lib/pq)
repro/bigalloc_listener.py            max-length (2.15 GB) crash PoC
repro/direct_listener.py              HTTP/-reply (wild variant) PoC
repro/fake_socks5.py                  SOCKS5-wrapped variant
repro/repro_direct.sh                 automated run (HTTP variant)
repro/repro_maxlen.sh                 automated run (max-length variant)
repro/pqfix_main.go                   N-concurrent-connection client (issue 3)
repro/pqfix_evil_pg.py                hostile server: http / d1g / d1gstream
repro/pqfix_setup.sh                  builds clients vs v1.12.3 and main
repro/pqfix_run_tests.sh              runs R1-R5 (issue 3)
repro/pqfix_sample_vm.sh              VmPeak sampler (issue 3)
repro/pqpanic_client.go               crash-test client: ping/query modes (issue 4)
repro/pqpanic_server.py               16 crafted-message modes (issue 4)
repro/pqpanic_setup.sh                builds clients vs v1.12.3 and main (issue 4)
repro/pqpanic_battery.sh              runs the 32-run matrix (issue 4)
repro/pqpanic_collect.sh              extracts panic signatures (issue 4)
evidence/incident_crash_snippet.txt   wild crash excerpt (from the real scan)
evidence/maxlen_nolimit.log           2.15 GB crash on a default system
evidence/maxlen_ulimit.log            2.15 GB crash under RLIMIT_AS
evidence/repro_http_1.41GB_ulimit.log exact wild bytes (0x5454502b) crash
evidence/payloads_via_proxy.txt       what actually goes through -socks5
evidence/payloads_http_direct.txt     pq startup arriving direct (bypass proof)
evidence/payloads_bigalloc_direct.txt same, max-length run
evidence/pqfix_r1.log                 v1.12.3 release: still crashes (HTTP)
evidence/pqfix_r2.log                 fixed main: HTTP correctly rejected
evidence/pqfix_r3.log                 fixed main: DataRow bypass -> crash
evidence/pqfix_r4.log                 fixed main 64-bit: 101.8 GB VmPeak
evidence/pqfix_r4_vmpeak.txt          measured VmPeak = 106,697,936 kB
evidence/pqfix_r5.log                 fixed main 64-bit: OOM-killed (exit 137)
evidence/pqfix_r5_dmesg.txt           kernel OOM-killer record
evidence/pqfix_evil_payloads.txt       payloads received by the hostile server
evidence/pqpanic_logs/                49 files: summary.txt + all 32 client runs
evidence/pqpanic_stolen_credentials.txt cleartext password harvest (issue 4)
```
