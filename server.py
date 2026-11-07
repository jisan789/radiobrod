#!/usr/bin/env python3
"""
Live Radio Broadcast Server (Pure Python)
Relays and broadcasts the live audio stream 24/7 to multiple concurrent listeners.
Stream Source: https://gains.reviveradio.net/proxy/bbmradio/stream
Includes a built-in Keep-Warm self-pinger to prevent Render free-tier idle sleeping.
"""

import collections
import json
import os
import queue
import socket
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

# Ensure stdout/stderr handles utf-8 safely on Windows/Linux
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Server & Stream Configuration
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")

# Upstream Live Audio Stream URL
STREAM_URL = os.environ.get(
    "STREAM_URL",
    "https://gains.reviveradio.net/proxy/bbmradio/stream"
).strip()

# Render automatically provides PORT (usually 10000)
PORT = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 3000))

# Render automatically sets RENDER_EXTERNAL_URL (e.g. https://my-radio.onrender.com)
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", os.environ.get("SELF_URL", "")).strip().rstrip("/")
# Render free tier sleeps after 15 mins of inactivity. Ping every 10 mins (600s).
PING_INTERVAL_SECONDS = int(os.environ.get("PING_INTERVAL", 600))

SERVER_BOOT_TIME = time.time()


# ---------------------------------------------------------------------------
# 1. Live Stream Relay & Multi-Client Broadcaster Engine
# ---------------------------------------------------------------------------
class LiveStreamBroadcaster:
    """
    Connects to the upstream live radio stream, maintains a single continuous
    audio connection, and distributes audio chunks to all connected listener clients.
    Includes an immediate priming ring buffer (~64 KB, ~2s of audio) for instant playback.
    """
    def __init__(self, stream_url):
        self.stream_url = stream_url
        self.clients = set()
        self.lock = threading.Lock()
        # Keep recent chunks for instantaneous playback priming on new client connections
        self.ring_buffer = collections.deque(maxlen=16)  # 16 x 4096 = 64KB (~2s at 256kbps)
        self.is_connected = False
        self.station_name = "BBM Radio"
        self.bitrate = 256
        self.genre = "Live Radio"
        self.total_bytes = 0
        self.last_connected_time = 0
        self.running = True

        # Start background stream consumer thread
        self.thread = threading.Thread(target=self._upstream_relay_loop, daemon=True)
        self.thread.start()

    def _upstream_relay_loop(self):
        chunk_size = 4096
        while self.running:
            try:
                print(f"[Radio Relay] Connecting to stream: {self.stream_url} ...")
                req = urllib.request.Request(
                    self.stream_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RadioRelayServer/2.0",
                        "Accept": "*/*",
                        "Icy-MetaData": "0",  # Receive pure MP3 stream without metadata byte injection
                    }
                )

                with urllib.request.urlopen(req, timeout=12) as resp:
                    icy_name = resp.headers.get("icy-name")
                    icy_br = resp.headers.get("icy-br")
                    icy_genre = resp.headers.get("icy-genre")

                    if icy_name:
                        # e.g. "rOne radio" or "bbmradio"
                        if "bbm" in icy_name.lower():
                            self.station_name = icy_name
                        else:
                            self.station_name = f"BBM Radio ({icy_name})"
                    else:
                        self.station_name = "BBM Radio"

                    if icy_br:
                        try:
                            self.bitrate = int(icy_br)
                        except ValueError:
                            pass

                    if icy_genre:
                        self.genre = icy_genre

                    self.is_connected = True
                    self.last_connected_time = time.time()
                    print(f"[Radio Relay] Upstream Connected! Station: '{self.station_name}' | Bitrate: {self.bitrate} kbps")

                    while self.running:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            print("[Radio Relay] Upstream stream disconnected (EOF). Reconnecting...")
                            break

                        self.total_bytes += len(chunk)

                        with self.lock:
                            self.ring_buffer.append(chunk)
                            active_clients = list(self.clients)

                        # Broadcast chunk to all connected listener client queues
                        for q in active_clients:
                            try:
                                q.put_nowait(chunk)
                            except queue.Full:
                                # Client network lagged behind; drop oldest chunk to stay synced with live audio
                                try:
                                    _ = q.get_nowait()
                                    q.put_nowait(chunk)
                                except Exception:
                                    pass

            except Exception as err:
                self.is_connected = False
                print(f"[Radio Relay] Stream connection error: {err}. Reconnecting in 3s...")
                time.sleep(3)

    def subscribe(self):
        """Register a new listener and return their queue along with priming audio burst."""
        q = queue.Queue(maxsize=100)
        with self.lock:
            burst_chunk = b"".join(self.ring_buffer)
            self.clients.add(q)
            count = len(self.clients)

        print(f"[Listener Connected] Active listeners: {count}")
        return q, burst_chunk

    def unsubscribe(self, q):
        with self.lock:
            self.clients.discard(q)
            count = len(self.clients)
        print(f"[Listener Disconnected] Active listeners: {count}")

    def get_status(self):
        with self.lock:
            listener_count = len(self.clients)

        stream_uptime = round(time.time() - self.last_connected_time, 1) if self.is_connected else 0

        return {
            "status": "broadcasting" if self.is_connected else "reconnecting",
            "uptimeSeconds": round(time.time() - SERVER_BOOT_TIME, 1),
            "streamUptimeSeconds": stream_uptime,
            "listeners": listener_count,
            "stationName": self.station_name,
            "bitrate": self.bitrate,
            "genre": self.genre,
            "streamUrl": self.stream_url,
            "sourceConnected": self.is_connected,
            "totalMegabytes": round(self.total_bytes / (1024 * 1024), 2)
        }


broadcaster = LiveStreamBroadcaster(STREAM_URL)


# ---------------------------------------------------------------------------
# 2. Keep-Warm Self-Pinger (Keeps Render Free Tier from Sleeping)
# ---------------------------------------------------------------------------
active_public_url = RENDER_EXTERNAL_URL


def keep_warm_worker():
    """Periodically sends an external HTTP request to itself so Render doesn't idle out."""
    global active_public_url
    time.sleep(60)

    while True:
        target_url = active_public_url
        if target_url:
            ping_url = f"{target_url}/healthz"
            try:
                req = urllib.request.Request(
                    ping_url,
                    headers={"User-Agent": "Render-KeepWarm/2.0 (Self-Pinger)"}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status == 200:
                        print(f"[Keep-Warm] Pinged {ping_url} -> 200 OK (Render service kept warm)")
            except Exception as e:
                print(f"[Keep-Warm] Ping failed for {ping_url}: {e}")
        else:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/healthz", timeout=5):
                    pass
            except Exception:
                pass

        time.sleep(PING_INTERVAL_SECONDS)


pinger_thread = threading.Thread(target=keep_warm_worker, daemon=True)
pinger_thread.start()


# ---------------------------------------------------------------------------
# 3. HTTP Server Request Handler
# ---------------------------------------------------------------------------
class RadioHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # Mute repetitive stream chunk / ping logs
        if "/stream" not in self.path and "/api/status" not in self.path and "/healthz" not in self.path:
            super().log_message(format, *args)

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        global active_public_url
        parsed = urlparse(self.path)
        path = parsed.path

        # Auto-learn public domain if RENDER_EXTERNAL_URL wasn't pre-set
        if not active_public_url and "Host" in self.headers:
            host = self.headers["Host"]
            if "onrender.com" in host or "render" in host:
                proto = self.headers.get("X-Forwarded-Proto", "https")
                active_public_url = f"{proto}://{host}"
                print(f"[Keep-Warm] Auto-detected public Render URL: {active_public_url}")

        # 1. Healthcheck / Ping endpoint (for Render health check & keep-warm)
        if path in ("/healthz", "/ping"):
            resp_body = json.dumps({
                "status": "ok",
                "broadcasting": broadcaster.is_connected,
                "uptime": round(time.time() - SERVER_BOOT_TIME, 1),
                "listeners": len(broadcaster.clients),
                "station": broadcaster.station_name
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            try:
                self.wfile.write(resp_body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            return

        # 2. Live Audio Broadcast Stream
        if path in ("/stream", "/live", "/stream.mp3"):
            try:
                self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except Exception:
                pass

            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Connection", "keep-alive")
            self.send_header("Accept-Ranges", "none")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("icy-name", broadcaster.station_name)
            self.send_header("icy-genre", broadcaster.genre)
            self.send_header("icy-br", str(broadcaster.bitrate))
            self.send_header("icy-sr", "44100")
            self.end_headers()

            q, burst = broadcaster.subscribe()
            try:
                # Send priming burst if available
                if burst:
                    self.wfile.write(burst)
                    self.wfile.flush()

                # Continuously relay real-time stream chunks
                while True:
                    try:
                        chunk = q.get(timeout=2.0)
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    except queue.Empty:
                        continue
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            finally:
                broadcaster.unsubscribe(q)
            return

        # 3. Live Status API
        if path == "/api/status":
            status_data = json.dumps(broadcaster.get_status()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache, no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(status_data)))
            self.end_headers()
            try:
                self.wfile.write(status_data)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            return

        # 4. Web Player Interface
        if path in ("/", "/index.html"):
            index_path = os.path.join(PUBLIC_DIR, "index.html")
            if os.path.isfile(index_path):
                with open(index_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                try:
                    self.wfile.write(content)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    pass
                return

        # 5. 404 Not Found
        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "9")
        self.end_headers()
        try:
            self.wfile.write(b"Not Found")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass


class RadioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def run():
    server = RadioServer(("0.0.0.0", PORT), RadioHandler)
    public_url_hint = active_public_url or f"http://localhost:{PORT}"
    print(f"""
======================================================
  [RADIO] 24/7 LIVE STREAM BROADCAST SERVER RUNNING!
======================================================
  > Source Stream:     {STREAM_URL}
  > Web Player:        {public_url_hint}/
  > Broadcast Stream:  {public_url_hint}/stream
  > Status API:        {public_url_hint}/api/status
  > Health Check:      {public_url_hint}/healthz
  > Keep-Warm Pinger:  Active (interval: {PING_INTERVAL_SECONDS}s)
======================================================
""")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Radio] Server stopped.")
        server.server_close()


if __name__ == "__main__":
    run()
