#!/usr/bin/env python3
"""
Bad Apple 16x16 Control Server
- Control page: /
- Read endpoint (cho HTTP Transmitter): /read
  → Mỗi lần GET /read (khi đang Start) sẽ trả frame hiện tại rồi tự +1 frame
- Status JSON: /status
"""

import http.server
import socketserver
import threading
import json
import os
from urllib.parse import urlparse, parse_qs

# ============== Config ==============
PORT = int(os.environ.get("PORT", 8080))   # Render dùng biến PORT
DATA_FILE = os.path.join(os.path.dirname(__file__), "badapple_16x16.txt")
TOTAL_FRAMES = 3205

# ============== Global state ==============
class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.playing = False
        self.current = 0          # 0-based
        self.frames = []          # list of 16-line strings

    def load_frames(self):
        print("Loading frames from", DATA_FILE)
        with open(DATA_FILE, "r") as f:
            lines = [line.rstrip("\n") for line in f]
        assert len(lines) == TOTAL_FRAMES * 16, f"Expected {TOTAL_FRAMES*16} lines, got {len(lines)}"
        self.frames = []
        for i in range(TOTAL_FRAMES):
            frame_lines = lines[i*16 : (i+1)*16]
            self.frames.append("\n".join(frame_lines))
        print(f"Loaded {len(self.frames)} frames")

    def get_frame_and_maybe_advance(self):
        """Trả frame hiện tại. Nếu đang playing thì +1 sau khi lấy."""
        with self.lock:
            text = self.frames[self.current]
            if self.playing:
                self.current = (self.current + 1) % TOTAL_FRAMES
            return text

    def get_status(self):
        with self.lock:
            return {
                "frame": self.current + 1,   # 1-based for display
                "total": TOTAL_FRAMES,
                "playing": self.playing
            }

    def start(self):
        with self.lock:
            self.playing = True

    def stop(self):
        with self.lock:
            self.playing = False

    def reset(self):
        with self.lock:
            self.current = 0
            self.playing = False

    def set_frame(self, n):
        with self.lock:
            if 0 <= n < TOTAL_FRAMES:
                self.current = n

state = State()

# ============== HTML Control Page ==============
CONTROL_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bad Apple 16×16 Control</title>
<style>
  :root {
    --bg: #0d1117;
    --card: #161b22;
    --border: #30363d;
    --text: #e6edf3;
    --muted: #8b949e;
    --green: #3fb950;
    --red: #f85149;
    --blue: #58a6ff;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 24px 16px;
  }
  h1 { font-size: 1.6rem; margin-bottom: 8px; letter-spacing: -0.02em; }
  .sub { color: var(--muted); font-size: 0.9rem; margin-bottom: 28px; }
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
    width: 100%;
    max-width: 420px;
    margin-bottom: 20px;
  }
  .preview-wrap { display: flex; justify-content: center; margin-bottom: 20px; }
  #preview {
    image-rendering: pixelated;
    image-rendering: crisp-edges;
    width: 256px; height: 256px;
    border: 2px solid var(--border);
    border-radius: 4px;
    background: #000;
  }
  .info { text-align: center; margin-bottom: 20px; }
  .frame-num {
    font-size: 2.2rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
  .frame-num span { color: var(--muted); font-weight: 400; font-size: 1.1rem; }
  .status { margin-top: 6px; font-size: 0.95rem; }
  .status.playing { color: var(--green); }
  .status.stopped { color: var(--red); }
  .btns { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }
  button {
    border: none; border-radius: 8px;
    padding: 12px 28px; font-size: 1rem; font-weight: 600;
    cursor: pointer; transition: opacity 0.15s, transform 0.1s;
  }
  button:active { transform: scale(0.97); }
  #btn-start { background: var(--green); color: #000; }
  #btn-stop  { background: var(--red); color: #fff; }
  #btn-reset { background: var(--border); color: var(--text); }
  .links {
    margin-top: 16px; font-size: 0.85rem;
    color: var(--muted); text-align: center; line-height: 1.6;
  }
  .links code {
    background: #21262d; padding: 2px 6px;
    border-radius: 4px; color: var(--blue); font-size: 0.8rem;
  }
  .slider-row {
    margin-top: 18px; display: flex; align-items: center; gap: 10px;
  }
  .slider-row label { font-size: 0.85rem; color: var(--muted); min-width: 50px; }
  input[type=range] { flex: 1; }
  .note { margin-top: 12px; font-size: 0.8rem; color: var(--muted); text-align: center; }
</style>
</head>
<body>
  <h1>Bad Apple 16×16</h1>
  <p class="sub">HTTP Control Panel</p>

  <div class="card">
    <div class="preview-wrap">
      <canvas id="preview" width="16" height="16"></canvas>
    </div>

    <div class="info">
      <div class="frame-num"><span id="cur">1</span> <span>/ <span id="total">3205</span></span></div>
      <div id="status" class="status stopped">● STOPPED</div>
    </div>

    <div class="btns">
      <button id="btn-start" onclick="doStart()">▶ Start</button>
      <button id="btn-stop"  onclick="doStop()">■ Stop</button>
      <button id="btn-reset" onclick="doReset()">↺ Reset</button>
    </div>

    <div class="slider-row">
      <label>Seek</label>
      <input type="range" id="seek" min="1" max="3205" value="1" oninput="seekPreview(this.value)">
    </div>

    <p class="note">Mỗi lần Transmitter GET /read → frame +1 (khi đang Start)</p>
  </div>

  <div class="links">
    <div>Transmitter đọc: <code id="read-url"></code></div>
    <div style="margin-top:6px">GET /read → 16 dòng 0/1 + tự chuyển frame tiếp theo</div>
  </div>

<script>
const canvas = document.getElementById('preview');
const ctx = canvas.getContext('2d');
const imgData = ctx.createImageData(16, 16);

function drawFrame(text) {
  const lines = text.trim().split('\\n');
  for (let y = 0; y < 16; y++) {
    const row = lines[y] || '0000000000000000';
    for (let x = 0; x < 16; x++) {
      const v = row[x] === '1' ? 255 : 0;
      const i = (y * 16 + x) * 4;
      imgData.data[i] = v;
      imgData.data[i+1] = v;
      imgData.data[i+2] = v;
      imgData.data[i+3] = 255;
    }
  }
  ctx.putImageData(imgData, 0, 0);
}

async function fetchStatus() {
  try {
    const r = await fetch('/status');
    const j = await r.json();
    document.getElementById('cur').textContent = j.frame;
    document.getElementById('total').textContent = j.total;
    document.getElementById('seek').value = j.frame;
    const st = document.getElementById('status');
    if (j.playing) {
      st.textContent = '● PLAYING (GET /read sẽ +1 frame)';
      st.className = 'status playing';
    } else {
      st.textContent = '● STOPPED';
      st.className = 'status stopped';
    }
  } catch (e) {}
}

async function refreshPreview() {
  try {
    const fr = await fetch('/preview');
    const txt = await fr.text();
    drawFrame(txt);
  } catch (e) {}
}

async function doStart() {
  await fetch('/start', { method: 'POST' });
  fetchStatus();
}
async function doStop() {
  await fetch('/stop', { method: 'POST' });
  fetchStatus();
}
async function doReset() {
  await fetch('/reset', { method: 'POST' });
  fetchStatus();
  refreshPreview();
}
async function seekPreview(val) {
  await fetch('/seek?f=' + val, { method: 'POST' });
  fetchStatus();
  refreshPreview();
}

document.getElementById('read-url').textContent = location.origin + '/read';
setInterval(() => { fetchStatus(); refreshPreview(); }, 300);
fetchStatus();
refreshPreview();
</script>
</body>
</html>
"""

# ============== Request Handler ==============
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/control":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(CONTROL_HTML.encode("utf-8"))

        elif path == "/read":
            # Transmitter: trả frame + tự +1 nếu đang playing
            text = state.get_frame_and_maybe_advance() + "\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(text.encode("utf-8"))

        elif path == "/preview":
            # Chỉ xem, KHÔNG advance
            with state.lock:
                text = state.frames[state.current] + "\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(text.encode("utf-8"))

        elif path == "/status":
            data = json.dumps(state.get_status())
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data.encode("utf-8"))

        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/start":
            state.start()
            self._ok()
        elif path == "/stop":
            state.stop()
            self._ok()
        elif path == "/reset":
            state.reset()
            self._ok()
        elif path == "/seek":
            qs = parse_qs(parsed.query)
            try:
                f = int(qs.get("f", ["1"])[0]) - 1
                state.set_frame(f)
            except Exception:
                pass
            self._ok()
        else:
            self.send_error(404)

    def _ok(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b"ok")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()


def main():
    state.load_frames()
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"\\n=== Bad Apple 16x16 Control ===")
        print(f"Control page : http://0.0.0.0:{PORT}/")
        print(f"Read endpoint: http://0.0.0.0:{PORT}/read")
        print(f"  → Mỗi GET /read (khi Start) sẽ +1 frame")
        print(f"Status JSON  : http://0.0.0.0:{PORT}/status")
        print("Press Ctrl+C to stop\\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\\nStopped.")

if __name__ == "__main__":
    main()
