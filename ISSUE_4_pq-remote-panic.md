# Remote crash: malformed server messages panic in `buf.go`/`encode.go` with no recovery — any lib/pq client killed by a single 5-byte message (12 variants)

**Versions:** every release through **v1.12.3** (2026-04-03) **and** current `main` (`45ac10e`, 2026-08-20) — tested both, identical behavior
**Environment:** Linux arm64, Raspberry Pi 4, 4 GB RAM — localhost-only PoC, deterministic
**Classification:** remote denial of service (CWE-248 / CWE-755). **Not RCE**: lib/pq contains no `unsafe`/`go:linkname` and Go aborts on panic before any memory corruption.

## Summary

`lib/pq` never recovers from panics (no `recover()` anywhere in production code; `database/sql` doesn't recover driver panics either). The network-data parsers in `buf.go` perform **unchecked slice operations on peer-supplied bytes**:

```go
func (b *readBuf) int32() (n int) {          // buf.go:15
	n = int(int32(binary.BigEndian.Uint32(*b)))   // panics if len < 4
	*b = (*b)[4:]                                  // panics if len < 4
}
func (b *readBuf) int16() (n int) {          // buf.go:28 — same, len < 2
func (b *readBuf) string() string {          // buf.go:34
	i := bytes.IndexByte(*b, 0)
	if i < 0 {
		panic(errors.New("pq: invalid message format; expected string terminator"))  // ← panics on peer data
	}
func (b *readBuf) next(n int) []byte {       // buf.go:44 — panics if n > len or n < 0
```

The same pattern exists in the value decoders (`encode.go:118` reads `s[0]` for `bool` without a length check; `encode.go:70` calls `binary.BigEndian.Uint64(s)` on short binary values) and in `error.go:129` (`parseError` loops `r.byte()`/`r.string()` over a possibly-empty buffer).

**A hostile PostgreSQL server (or MITM on a plaintext connection) can therefore terminate any lib/pq client at will with a single tiny message — no authentication, no memory pressure, no timing requirements.**

## Proof (Raspberry Pi, 16 crafted-message modes × 2 versions = 32 runs)

Hostile server sends one crafted reply to the startup packet (or, for query-stage modes, completes the handshake and then replies to the client's query):

| Mode | Bytes sent | Crash (both versions) | Panic location |
|---|---|---|---|
| `auth_empty` | `R 00000004` | ✅ `index out of range [3] with length 0` | `buf.go:16` ← `conn.go` auth |
| `auth_short` | `R 00000005 00` | ✅ `index out of range [3] with length 1` | `buf.go:16` |
| `key_empty` | `K 00000004` | ✅ `index out of range [3] with length 0` | `buf.go:16` ← BackendKeyData |
| `neg_empty` | `v 00000004` | ✅ `index out of range [3] with length 0` | `buf.go:16` ← NegotiateProtocolVersion |
| `ps_empty` | `S 00000004` | ✅ `pq: invalid message format; expected string terminator` | `buf.go:37` ← ParameterStatus |
| `ps_nonull` | `S 00000005 41` | ✅ same explicit panic | `buf.go:37` |
| `err_nonull` | `E 00000008 41414141` | ✅ same explicit panic | `buf.go:37` ← `error.go:130` parseError |
| `rfq_empty` | `Z 00000004` | ✅ `slice bounds out of range [1:0]` | `buf.go:46/51` ← ReadyForQuery |
| `cc_empty` | `C 00000004` (post-HS) | ✅ `expected string terminator` | `buf.go:37` ← parseComplete |
| `rd_empty` | `T 00000004` (post-HS) | ✅ `index out of range [1] with length 0` | `buf.go:29` ← RowDescription parse |
| `qbool` | `T` bool col + `D` **empty value** | ✅ `index out of range [0] with length 0` | `encode.go:118` |
| `qbin` | `T` int8 binary col + `D` 2-byte value | ✅ `index out of range [7] with length 2` | `encode.go:70` binaryDecode |
| `notif_empty` | `A 00000004` | ⚠️ silent only because no `NotificationHandler` is registered — **panics as soon as an app registers one** (`recvNotification` → `int32()`), otherwise the connection hangs until EOF | `buf.go:16` |
| `notice_empty` | `N 00000004` | ⚠️ same, via `NoticeHandler` → `parseError` | `buf.go:46` |
| `ok` | valid handshake | ✅ control: succeeds (harness validates) | — |

Full matrix (both `pqtest_v1123` and `pqtest_main` rows identical): `evidence/pqpanic_logs/summary.txt`; representative stacks: `pqtest_main_auth_empty.log`, `pqtest_main_ps_nonull.log`, `pqtest_main_qbool.log`, `pqtest_main_qbin.log`, `pqtest_main_cc_empty.log`, `pqtest_main_rd_empty.log`.

**Worst part:** the OOM length-cap fix from `b125f757` does not address any of this — these messages are all ≤ 8 bytes and pass every length check. The crash is **instant and needs essentially no resources**, so it works on any host regardless of RAM (where the OOM variant needs memory pressure).

**fscan impact:** `fscan -m postgresql` against any hostile host dies with exit code 2 (panic) before completing a single credential test — a scanner-wide DoS from one malicious port-5432 banner.

## Reproduction

```bash
python3 panic_server.py auth_empty 5433 &     # or any mode from the table
./pqtest ping 5433 Secret123                  # built against lib/pq v1.12.3 or main
# -> panic: runtime error: index out of range [3] with length 0 (buf.go:16), exit 2
```

Client (`pqtest.go`), server (`panic_server.py`), and the full 32-run battery script accompany this report.

## Suggested fix

1. Make every `readBuf` accessor bounds-checked and **return errors** instead of panicking (`int32/int16/byte/next/string`), propagating through `recvMessage`/`startup`/`parseError` as protocol errors.
2. At minimum, validate `len(*b)` before each access and replace the `buf.go:37` panic with an error return.
3. In `decode`: guard `T_bool` (`len(s) >= 1`) and `binaryDecode` (length per OID, like `decodeUUIDBinary` already does).
4. Consider a defensive `recover()` at the connection-read boundary that converts panics into `driver.ErrBadConn`, so future parser bugs degrade to a failed connection instead of process death.

## Also observed during this audit (not a lib/pq bug, protocol behavior worth documenting)

With `sslmode=disable` (or `require`, which does not verify), a hostile server can request `AuthenticationCleartextPassword` and the client dutifully sends its password in the clear — captured in `evidence/pqpanic_stolen_credentials.txt` (`p\x00\x00\x00\x0eSecret123\x00`). This matches libpq, but scanners that put dictionary passwords into DSNs and connect to untrusted hosts should be aware the dictionary is exfiltratable by any target that asks.
