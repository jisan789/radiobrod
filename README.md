# 📻 Live Radio Broadcast Server (Pure Python)

A synchronized, continuous-loop live audio streaming server built with **pure Python** (zero external pip packages or dependencies required).

---

## 🎯 How It Works

1. **Server-Side Broadcast Engine:**
   - The server parses `songs.mp3` directly into MPEG-1 Layer III audio frames.
   - A background thread continuously broadcasts frames in real time according to the system clock.
2. **True Synchronized Radio:**
   - When any user opens the stream URL, they immediately start listening from the **current live timestamp** — not from the beginning.
   - All listeners hear the exact same audio at the exact same moment.
3. **Infinite Seamless Looping:**
   - When the song finishes, the server wraps around to the start of the audio frames and keeps broadcasting into active connections without disconnecting any listener.

---

## 🚀 How to Run

### 1. Start the Server
Run with Python:
```bash
python server.py
```

Optional custom port:
```bash
python server.py 8080
```

### 2. Available Endpoints

| Endpoint | Description |
| :--- | :--- |
| **`http://localhost:3000/`** | Web player with a live visualizer, active listener count, and one-click play. |
| **`http://localhost:3000/stream`** | Raw live MP3 audio stream for direct playback in browsers, mobile devices, VLC, etc. |
| **`http://localhost:3000/api/status`** | Real-time JSON status (listener count, current position, total duration, loop count). |

---

## 🌐 Listening from Other Devices or Over the Internet

### On Local Network (Wi-Fi / LAN)
Find your computer's local IP address (`ipconfig` on Windows, e.g. `192.168.1.15`). Any device on the same Wi-Fi can listen directly at:
```
http://192.168.1.15:3000/
http://192.168.1.15:3000/stream
```

### Over the Internet (Public Stream URL)
You can share your live radio station with anyone across the internet using any tunneling tool, for example Cloudflare Tunnel:
```bash
npx cloudflared tunnel --url http://localhost:3000
```
This gives you a public HTTPS URL (such as `https://random-name.trycloudflare.com/stream`) that anyone in the world can open to tune in live.

---

## 🎛️ Changing the Audio File
Replace `songs.mp3` with your own MP3 file, or update `AUDIO_FILE` in [`server.py`](file:///c:/Users/Jisan/Desktop/radio/server.py).
