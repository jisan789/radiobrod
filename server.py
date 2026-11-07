#!/usr/bin/env python3
"""
Live Radio Broadcast Server (Pure Python)
Broadcasts a continuous, synchronized loop of an MP3 audio file 24/7.
Includes a built-in Keep-Warm self-pinger to prevent Render free-tier idle sleeping.
"""

import os
import sys
import time
import json
import queue
import socket
import threading
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# Ensure stdout/stderr handles utf-8 safely on Windows/Linux
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Server & Environment Configuration
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_FILE = os.path.join(BASE_DIR, "songs.mp3")
PUBLIC_DIR = os.path.join(BASE_DIR, "public")

# Render automatically provides PORT (usually 10000)
PORT = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 3000))

# Render automatically sets RENDER_EXTERNAL_URL (e.g. https://my-radio.onrender.com)
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", os.environ.get("SELF_URL", "")).strip().rstrip("/")
# Render free tier sleeps after 15 mins of inactivity. Ping every 10 mins (600s).
PING_INTERVAL_SECONDS = int(os.environ.get("PING_INTERVAL", 600))

SERVER_BOOT_TIME = time.time()

# ---------------------------------------------------------------------------
# 1. MP3 Frame Parser
# ---------------------------------------------------------------------------
BITRATES = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
SAMPLE_RATES = [44100, 48000, 32000]

def load_mp3_frames(file_path):
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    with open(file_path, "rb") as f:
        buf = f.read()

    # Skip ID3v2 header if present
    offset = 0
    if buf[:3] == b"ID3":
        id3_size = (buf[6] << 21) | (buf[7] << 14) | (buf[8] << 7) | buf[9]
        offset = 10 + id3_size

    frames = []
    curr = offset
    total_len = len(buf)

    while curr < total_len - 4:
        # Check for MP3 sync word (0xFF followed by top 3 bits set)
        if buf[curr] == 0xFF and (buf[curr + 1] & 0xE0) == 0xE0:
            b2 = buf[curr + 2]
            bitrate_idx = (b2 >> 4) & 15
            samplerate_idx = (b2 >> 2) & 3
            padding = (b2 >> 1) & 1

            br = BITRATES[bitrate_idx] * 1000 if bitrate_idx < len(BITRATES) else 0
            sr = SAMPLE_RATES[samplerate_idx] if samplerate_idx < len(SAMPLE_RATES) else 0

            if br and sr:
                frame_len = (144 * br) // sr + padding
                if curr + frame_len <= total_len:
                    frames.append(buf[curr : curr + frame_len])
                    curr += frame_len
                    continue
        curr += 1

    if not frames:
        raise ValueError("No valid MP3 frames detected in audio file.")

    return frames

print(f"[Radio] Loading audio file: {AUDIO_FILE}...")
FRAMES = load_mp3_frames(AUDIO_FILE)
FRAME_DURATION = 1152 / 44100  # ~0.026122 seconds per frame
TOTAL_DURATION = len(FRAMES) * FRAME_DURATION
print(f"[Radio] Loaded {len(FRAMES)} frames (~{TOTAL_DURATION:.2f} seconds).")

# ---------------------------------------------------------------------------
# 2. Live Broadcast Engine (Infinite 24/7 Loop)
# ---------------------------------------------------------------------------
class RadioBroadcaster:
    def __init__(self, frames, frame_duration):
        self.frames = frames
        self.frame_duration = frame_duration
        self.total_frames = len(frames)
        self.total_duration = self.total_frames * frame_duration
        self.start_time = time.time()
        self.last_index = 0
        self.clients = set()
        self.lock = threading.Lock()
        self.running = True

        # Start broadcaster background thread
        self.thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self.thread.start()

    def get_current_frame_index(self):
        elapsed = time.time() - self.start_time
        total_elapsed_frames = int(elapsed / self.frame_duration)
        return total_elapsed_frames % self.total_frames

    def get_status(self):
        curr_frame = self.get_current_frame_index()
        curr_pos = curr_frame * self.frame_duration
        elapsed = time.time() - self.start_time
        loop_count = int(elapsed / self.total_duration)

        with self.lock:
            listener_count = len(self.clients)

        return {
            "status": "broadcasting",
            "uptimeSeconds": round(time.time() - SERVER_BOOT_TIME, 1),
            "listeners": listener_count,
            "currentPosition": round(curr_pos, 1),
            "duration": round(self.total_duration, 1),
            "loopCount": loop_count,
            "trackName": os.path.basename(AUDIO_FILE)
        }

    def subscribe(self):
        """Register a new listener and return their queue and priming burst frames."""
        q = queue.Queue(maxsize=120)
        curr = self.get_current_frame_index()

        # Prime client with ~50 recent frames (~1.3s) for instantaneous playback
        burst_count = min(50, self.total_frames)
        burst_frames = []
        for i in range(burst_count, 0, -1):
            idx = (curr - i + self.total_frames) % self.total_frames
            burst_frames.append(self.frames[idx])
        burst_chunk = b"".join(burst_frames)

        with self.lock:
            self.clients.add(q)
            count = len(self.clients)

        print(f"[Listener Connected] Active listeners: {count}")
        return q, burst_chunk

    def unsubscribe(self, q):
        with self.lock:
            self.clients.discard(q)
            count = len(self.clients)
        print(f"[Listener Disconnected] Active listeners: {count}")

    def _broadcast_loop(self):
        while self.running:
            target = self.get_current_frame_index()
            frames_to_send = []

            if target >= self.last_index:
                frames_to_send = self.frames[self.last_index : target + 1]
            else:
                # Loop back to frame 0 (continuous 24/7 repeating)
                frames_to_send = self.frames[self.last_index :] + self.frames[: target + 1]

            self.last_index = (target + 1) % self.total_frames

            if frames_to_send:
                chunk = b"".join(frames_to_send)
                with self.lock:
                    active = list(self.clients)

                for q in active:
                    try:
                        q.put_nowait(chunk)
                    except queue.Full:
                        # Client network lagged; drop oldest chunk to stay synchronized with live audio
                        try:
                            _ = q.get_nowait()
                            q.put_nowait(chunk)
                        except Exception:
                            pass

            time.sleep(0.04)

broadcaster = RadioBroadcaster(FRAMES, FRAME_DURATION)

# ---------------------------------------------------------------------------
# 3. Keep-Warm Self-Pinger (Keeps Render Free Tier from Sleeping)
# ---------------------------------------------------------------------------
active_public_url = RENDER_EXTERNAL_URL

def keep_warm_worker():
    """Periodically sends an external HTTP request to itself so Render doesn't idle out."""
    global active_public_url
    # Wait 60 seconds after boot before first ping cycle
    time.sleep(60)

    while True:
        target_url = active_public_url
        if target_url:
            ping_url = f"{target_url}/healthz"
            try:
                req = urllib.request.Request(
                    ping_url,
                    headers={"User-Agent": "Render-KeepWarm/1.0 (Self-Pinger)"}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status == 200:
                        print(f"[Keep-Warm] Pinged {ping_url} -> 200 OK (Render service kept warm)")
            except Exception as e:
                print(f"[Keep-Warm] Ping failed for {ping_url}: {e}")
        else:
            # If not yet detected, check local health endpoint
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/healthz", timeout=5):
                    pass
            except Exception:
                pass

        time.sleep(PING_INTERVAL_SECONDS)

pinger_thread = threading.Thread(target=keep_warm_worker, daemon=True)
pinger_thread.start()

# ---------------------------------------------------------------------------
# 4. HTTP Server Request Handler
# ---------------------------------------------------------------------------
class RadioHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # Mute repetitive streaming chunk logs from cluttering Render log stream
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
                "broadcasting": True,
                "uptime": round(time.time() - SERVER_BOOT_TIME, 1)
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

        # 2. Live MP3 Audio Stream
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
            self.send_header("icy-name", "Live Radio Stream")
            self.send_header("icy-description", "Synchronized Continuous Broadcast 24/7")
            self.end_headers()

            q, burst = broadcaster.subscribe()
            try:
                # Send priming burst
                if burst:
                    self.wfile.write(burst)
                    self.wfile.flush()

                # Stream live frames continuously in real time
                while True:
                    try:
                        chunk = q.get(timeout=1.0)
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
  [RADIO] 24/7 LIVE BROADCAST SERVER RUNNING!
======================================================
  > Web Player:        {public_url_hint}/
  > Live Stream URL:   {public_url_hint}/stream
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
