# 📻 Live Radio Broadcast Server (Pure Python — 24/7 on Render)

A continuous live audio streaming relay server built with **pure Python** (zero third-party dependencies). Relays and broadcasts the live audio stream from **[BBM Radio](https://gains.reviveradio.net/proxy/bbmradio/stream)** 24/7 to multiple listeners. Configured for **continuous operation on Render's free tier**.

---

## 🎯 Key Features

1. **24/7 Live Stream Relay:**
   - Connects to `https://gains.reviveradio.net/proxy/bbmradio/stream` and broadcasts audio simultaneously to all connected listeners.
   - Built-in instant priming buffer (~64 KB, ~2s) for instant playback when listeners connect.
   - Automatic reconnect with retry logic if upstream connection drops.
2. **🎙️ Admin DJ Studio Workstation & Manual Speak (Passcode: 8099):**
   - **Passcode Protected:** Click "DJ Studio (Admin)" in the top header and enter passcode `8099` to unlock the studio broadcast console.
   - **Manual Speak (On-Air):** Push-to-talk or toggle microphone to go live on air with real-time VU meter.
   - **Smart Song Auto-Ducking:** Automatically lowers radio music volume when you speak (configurable ducking depth, e.g. 20%) and smooth crossfades back up.
   - **Multi-Channel Studio Mixer:**
     - **CH 1:** Host Mic with gain fader, broadcast warmth EQ, FM limiter, and booth reverb.
     - **CH 2:** Live Song fader (0% - 150%), quick duck, and crossfaders.
     - **CH 3:** Studio BGM Beds (Late Night Jazz, Lo-Fi, FM Groove, Ambient, or custom MP3 upload).
     - **CH 4:** Live Studio Sounds & Soundboard (Air Horn, Applause/Cheer, Station Jingle, Turntable Scratch, Rimshot, Booth Room Tone, and Cough Mute).
   - **Dual Stereo VU Meters & Spectrum Visualizer** for a real broadcast studio booth vibe.
3. **Built-in Keep-Warm Self-Pinger:**
   - Render's free tier spins down after 15 minutes of inactivity.
   - [`server.py`](file:///c:/Users/Jisan/Desktop/radio/server.py) includes a background thread that automatically self-pings the public endpoint every **10 minutes** via `RENDER_EXTERNAL_URL` (or auto-detected domain), keeping the service awake and playing 24/7 within Render's 750 free monthly hours.
4. **Zero Configuration Deployment:**
   - Includes [`render.yaml`](file:///c:/Users/Jisan/Desktop/radio/render.yaml) and [`requirements.txt`](file:///c:/Users/Jisan/Desktop/radio/requirements.txt) for 1-click Render web service deployment.
   - Standard `/healthz` endpoint for Render health checks.
5. **Environment Configuration:**
   - Configurable stream URL via the `STREAM_URL` environment variable.
   - Configurable admin passcode via `ADMIN_PASSCODE` (default: `8099`).

---

## 🚀 Deploying to Render (Step-by-Step)

### Option 1: Connect GitHub Repo to Render
1. Push this repository to your GitHub.
2. Go to [dashboard.render.com](https://dashboard.render.com) and click **"New +" → "Web Service"**.
3. Select your GitHub repository.
4. Render will auto-fill the settings:
   - **Environment:** `Python`
   - **Build Command:** *(leave empty or `pip install -r requirements.txt`)*
   - **Start Command:** `python server.py`
   - **Plan:** `Free`
5. Click **"Deploy Web Service"**.

---

## 📡 Live Stream Endpoints

Once deployed on Render, your radio will be live at:

| URL | Description |
| :--- | :--- |
| `https://<your-service>.onrender.com/` | Web player with vinyl visualizer and live listener stats. |
| `https://<your-service>.onrender.com/stream` | Direct raw live audio stream (browser, VLC, mobile, apps). |
| `https://<your-service>.onrender.com/api/status` | JSON status (listeners, station name, bitrate, uptime). |
| `https://<your-service>.onrender.com/healthz` | Lightweight health check and keep-warm ping target. |

---

## 💡 External Keep-Warm Backup (Recommended)

While the server has an internal self-pinger, Render occasionally blocks self-originating requests on certain network configurations. To guarantee 100% 24/7 uptime:
1. Create a free account on [cron-job.org](https://cron-job.org) or [uptimerobot.com](https://uptimerobot.com).
2. Set up a free monitor to ping:
   ```
   https://<your-service>.onrender.com/healthz
   ```
   every **10 minutes**.
