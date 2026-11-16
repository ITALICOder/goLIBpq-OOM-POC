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
