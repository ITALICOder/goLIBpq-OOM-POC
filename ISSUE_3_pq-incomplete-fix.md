# Incomplete fix for unbounded allocation in `recvMessage`: `ValidLongMessageType` bypass + concurrency still allows remote OOM (up to ~100 GB demanded)

**Version:** `main` branch (`45ac10e`, 2026-08-20) — includes commit `b125f757` *"Only check error length during startup, limit response size for some types"* (2026-07-11)
**Also affects:** every released version (latest: **v1.12.3**, 2026-04-03) — they contain **no length check at all**
**Environment:** Debian armhf/arm64, Raspberry Pi 4, 4 GB RAM — reproduced deterministically with localhost PoCs
**Classification:** remote memory-exhaustion DoS (not a buffer overflow, not RCE)

## Summary

Commit `b125f757` added a length cap to `recvMessage`, but the cap only applies when `!proto.ValidLongMessageType(t)`:

```go
n := int(binary.BigEndian.Uint32(x[1:])) - 4
...
if !proto.ValidLongMessageType(t) && n > proto.MaxMsgLen {   // MaxMsgLen = 30_000
    return 0, fmt.Errorf("pq: lost synchronization ...")
}
...
y = make([]byte, n)   // ← for ValidLongMessageType: NO cap at all
```

`ValidLongMessageType` includes `DataRow ('D')`, `RowDescription ('T')`, `ErrorResponse ('E')`, `CopyData ('d')`, `FunctionCallResponse ('V')`, `Notice ('N')`, `Notification ('A')`. A hostile server simply uses one of those type bytes and the allocation is **exactly as uncapped as before** — the peer fully controls `n` (up to `uint32`, i.e. ~4.29 GB per message on 64-bit).

Additionally, even a correct per-message cap would not be sufficient: the peer can open **many connections concurrently**, each declaring the maximum allowed size. N × cap quickly exceeds host RAM.

## Proof (all runs on the same 4 GB Pi, localhost-only)

Five-run harness (`client*.go` opens N concurrent `database/sql` connections and Pings each, like a scanner's credential test; `evil_pg.py` is the hostile server):

| # | pq version | Server reply | Result |
|---|---|---|---|
| R1 | **v1.12.3 (latest release)** | `HTTP/1.1 403 ...` | **crash, exit 2**: `runtime: out of memory: cannot allocate 1417674752-byte block` → `makeslice(0x5454502b)` → `recvMessage` |
| R2 | main (fixed) | `HTTP/1.1 403 ...` | clean error: `pq: lost synchronization with server: got message type "(H) CopyOutResponse", length 1414811691` — the fix works **only** for non-valid-long types |
| R3 | **main (fixed)** | **`'D'` + length 1 GiB × 100 conns** | **crash, exit 2**: `runtime: out of memory: cannot allocate 1073741824-byte block` → `makeslice(0x40000000)` → `recvMessage` at `conn.go:1131` — **bypass** |
| R4 | main (fixed), 64-bit | `'D'` + length 1 GiB × 100 conns | no crash (overcommit), but **VmPeak = 106,697,936 kB ≈ 101.8 GB** of address space demanded by 5-byte replies |
| R5 | main (fixed), 64-bit | `'D'` + 1 GiB + payload streamed | **killed by the kernel OOM killer, exit 137**: `Out of memory: Killed process 6531 (clientmain_arm6) total-vm:108460768kB` |

So the bypass works in two distinct ways:

1. **Type-byte bypass (R3):** `'H'` (HTTP) is rejected, `'D'` (DataRow) is not — the fix is one byte away from being defeated. On 32-bit builds (which is what fscan ships for ARM) the very first concurrent allocations crash the process with the Go runtime's `fatal error: out of memory`.
2. **Concurrency × cap (R4/R5):** even if every message were capped at the RFC-ish 1 GB the check was meant to enforce, 100 concurrent connections × 1 GB = **100 GB** — measured at 101.8 GB VmPeak, then the kernel OOM-kills the process. Scanners (like fscan) routinely run 5–64 concurrent credential tests against hundreds of hosts.

## Root cause

`recvMessage` trusts a peer-supplied 32-bit length and turns it into `make([]byte, n)` with no:

- global ceiling appropriate for the process (PostgreSQL messages that matter here — auth, error, parameter status — are tiny; even real `DataRow` messages are bounded by the *client's* result expectations, not by the peer's word),
- accounting for concurrent connections doing the same,
- checked arithmetic (`n < 4` wraparound still possible on the `ErrorResponse` plain-text path).

## Reproduction

```bash
python3 evil_pg.py d1g 5433 &          # hostile server: replies b'D' + uint32(1GiB+4)
./clientmain_arm 100 5433 15           # 100 concurrent pq connections -> fatal error: out of memory (exit 2)
./clientmain_arm64 100 5433 15         # 64-bit: VmPeak ~101.8 GB
python3 evil_pg.py d1gstream 5433 &    # + streams payload -> kernel OOM kill (exit 137)
```

Scripts and full logs accompany this report (`repro/pqfix_*`, `evidence/pqfix_r1..r5.log`, `pqfix_r5_dmesg.txt`, `pqfix_r4_vmpeak.txt`).

## Suggested fix

- Apply the length ceiling to **all** message types (or at minimum make `MaxMsgLen` an absolute cap that `ValidLongMessageType` cannot bypass — a `DataRow` larger than a sane buffer limit is not something pq should materialize in one `make` anyway).
- Prefer streaming/incremental reads for large messages instead of one peer-sized allocation.
- Enforce a **per-connection memory budget** or a cap on concurrently-open oversized reads; a scanner process must not be able to lose 100 GB of address space to N×5-byte replies.
- Keep the `n < 4` wraparound check for every type, not just the `ErrorResponse` startup path.

## Relation to fscan

fscan vendors `lib/pq` and crashes identically in the wild (separate report against shadow1ng/fscan). Updating fscan to current `main` only fixes the HTTP variant; the DataRow/concurrency variants remain exploitable against fscan's `postgresql` plugin exactly as shown here.
