#!/bin/bash
# bench.sh - compare shurl vs curl request latency.
# Usage: ./bench.sh [ITERATIONS]   (default: 100)
#
# Both tools are forced to HTTP/1.0 (no keep-alive) so the comparison is
# protocol-equivalent.  The dominant shurl cost is bash process startup.

set -euo pipefail

N="${1:-100}"
SHURL="$(cd "$(dirname "$0")" && pwd)/shurl"

# Pick a free port.
PORT=$(python3 -c "
import socket
s = socket.socket()
s.bind(('', 0))
print(s.getsockname()[1])
s.close()
")
BASE="http://127.0.0.1:${PORT}"

# Start an embedded HTTP/1.0 server (inline, no extra files needed).
export PORT
python3 <<'PY' &
import os, http.server, socketserver

class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    def do_GET(self):
        body = b"hello\n" if self.path == "/small" else b"x" * 1048576
        self.send_response(200)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200)
        self.send_header("Content-Length", 2)
        self.end_headers()
        self.wfile.write(b"ok")

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", int(os.environ["PORT"])), H) as srv:
    srv.serve_forever()
PY
SRV_PID=$!
trap "kill ${SRV_PID} 2>/dev/null; wait ${SRV_PID} 2>/dev/null" EXIT

# Wait for server to be ready.
for _ in $(seq 20); do
    curl -sf "${BASE}/small" >/dev/null 2>&1 && break
    sleep 0.1
done

# Run N iterations of a command and print elapsed milliseconds.
time_ms() {
    local n=$1; shift
    local t0 t1
    t0=$(date +%s%3N)
    for _ in $(seq "$n"); do "$@" >/dev/null 2>&1; done
    t1=$(date +%s%3N)
    echo $((t1 - t0))
}

# Print one result row: label, shurl total ms, curl total ms.
row() {
    local label=$1 s=$2 c=$3
    printf "  %-22s  %8.1f ms  %8.1f ms  %5.1fx\n" \
        "$label" \
        "$(awk "BEGIN{printf \"%.1f\", $s / $N}")" \
        "$(awk "BEGIN{printf \"%.1f\", $c / $N}")" \
        "$(awk "BEGIN{printf \"%.1f\", $s / $c}")"
}

echo ""
echo "shurl vs curl -- ${N} iterations each, HTTP/1.0, loopback"
echo ""
printf "  %-22s  %10s  %10s  %7s\n" "scenario" "shurl/req" "curl/req" "ratio"
printf "  %-22s  %10s  %10s  %7s\n" "--------" "---------" "--------" "-------"

row "GET small (6 B)" \
    "$(time_ms "$N" bash "$SHURL" "$BASE/small")" \
    "$(time_ms "$N" curl -s --http1.0 "$BASE/small")"

row "GET large (1 MB)" \
    "$(time_ms "$N" bash "$SHURL" "$BASE/large")" \
    "$(time_ms "$N" curl -s --http1.0 "$BASE/large")"

row "POST small body" \
    "$(time_ms "$N" bash "$SHURL" -d "x=1" "$BASE/small")" \
    "$(time_ms "$N" curl -s --http1.0 -d "x=1" "$BASE/small")"

echo ""
echo "Ratio = shurl time / curl time (lower is better for shurl)."
echo "shurl overhead is dominated by bash process startup, not I/O."
