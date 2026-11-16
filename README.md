# goLIBpq-OOM-POC
Still after an attempt to fix the previous bug we found in fscan that was related to and older version "pre-fix" for go lib/pq, the patch actually didnt resolve anything at all,here the demostration:

Raspberry proof (5 runs, all captured)
#	Version	Reply	Result
R1	v1.12.3 (latest release)	HTTP	💥 exit=2, makeslice(0x5454502b) — release still crashes
R2	fixed main	HTTP	✅ rejected cleanly — fix works only here
R3	fixed main	'D' + 1 GiB × 100 conns	💥 exit=2, makeslice(0x40000000) @ conn.go:1131 — bypass
R4	fixed main 64-bit	same	VmPeak = 106,697,936 kB ≈ 101.8 GB demanded by 5-byte replies
R5	fixed main 64-bit	+ streaming	💥 exit=137, kernel OOM-killer: total-vm:108460768kB
