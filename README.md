# 📻 Live Radio Broadcast Server (Pure Python — 24/7 on Render)

A continuous, synchronized live audio streaming server built with **pure Python** (zero third-party pip dependencies). Configured for **24/7 continuous operation on Render's free tier**.

---

## 🎯 Key Features

1. **Synchronized 24/7 Live Broadcast:**
   - Every visitor listens from the server's current live timestamp.
   - When the song finishes, it immediately loops back to the start without dropping any active listeners.
2. **Built-in Keep-Warm Self-Pinger:**
   - Render's free tier spins down after 15 minutes of inactivity.
   - [`server.py`](file:///c:/Users/Jisan/Desktop/radio/server.py) includes a background thread that automatically self-pings the public endpoint every **10 minutes** via `RENDER_EXTERNAL_URL` (or auto-detected domain), keeping the service awake and playing 24/7 within Render's 750 free monthly hours.
3. **Zero Configuration Deployment:**
   - Includes [`render.yaml`](file:///c:/Users/Jisan/Desktop/radio/render.yaml) and [`requirements.txt`](file:///c:/Users/Jisan/Desktop/radio/requirements.txt) for 1-click Render web service deployment.
   - Standard `/healthz` endpoint for Render health checks.

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
| `https://<your-service>.onrender.com/` | Web player with vinyl visualizer and listener stats. |
| `https://<your-service>.onrender.com/stream` | Direct raw live audio stream (browser, VLC, mobile, apps). |
| `https://<your-service>.onrender.com/api/status` | JSON status (listeners, current track position, loop count). |
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
