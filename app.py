# app.py - Entry point chính cho Render Web Service
# Tác giả: MADE BY Bao Huy
# Chạy web + API + bot trong cùng process
# Start Command: gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120

# ============================================================
# IMPORT
# ============================================================

import os
import sys
import time
import json
import signal
import logging
import threading
import traceback
from datetime import datetime

# ============================================================
# DEBUG KHỞI ĐỘNG - IN RA LOG ĐỂ KIỂM TRA
# ============================================================

print("=" * 60, flush=True)
print("[APP] Khởi động Key Server", flush=True)
print(f"[APP] Python: {sys.version.split()[0]}", flush=True)
print(f"[APP] PORT env: {os.environ.get('PORT', 'CHƯA SET')}", flush=True)
print(f"[APP] DATA_DIR: {os.environ.get('DATA_DIR', './data')}", flush=True)
print(f"[APP] CWD: {os.getcwd()}", flush=True)
print(f"[APP] Files: {sorted(os.listdir('.'))[:20]}", flush=True)
print(f"[APP] BOT_TOKEN: {'SET' if os.environ.get('BOT_TOKEN') else 'MISSING'}", flush=True)
print(f"[APP] USE_WEBHOOK: {os.environ.get('USE_WEBHOOK', 'false')}", flush=True)
print(f"[APP] ENABLE_BOT: {os.environ.get('ENABLE_BOT', 'true')}", flush=True)
print("=" * 60, flush=True)

# ============================================================
# CẤU HÌNH LOGGING
# ============================================================

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("app")

# ============================================================
# IMPORT FLASK
# ============================================================

try:
    from flask import Flask, jsonify, request
    log.info("Flask import OK")
except Exception as e:
    log.error(f"Flask import FAIL: {e}")
    log.error(traceback.format_exc())
    sys.exit(1)

# ============================================================
# KHỞI TẠO APP
# ============================================================

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev_secret_key_change_me")
app.config["JSON_SORT_KEYS"] = False
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

# ============================================================
# IMPORT MODULE NỘI BỘ (AN TOÀN - KHÔNG CHẶN KHỞI ĐỘNG)
# ============================================================

_modules_status = {}

def _try_import(name):
    try:
        mod = __import__(name)
        _modules_status[name] = "OK"
        log.info(f"Import {name}: OK")
        return mod
    except Exception as e:
        _modules_status[name] = f"FAIL: {e}"
        log.warning(f"Import {name}: FAIL - {e}")
        return None

db_mod = _try_import("db")
key_mod = _try_import("key")
auth_mod = _try_import("auth")
apikey_mod = _try_import("apikey")
cache_mod = _try_import("cache")
web_mod = _try_import("web")
api_mod = _try_import("api")
bot_mod = _try_import("bot")

# ============================================================
# ĐĂNG KÝ BLUEPRINT
# ============================================================

if web_mod and hasattr(web_mod, "register"):
    try:
        web_mod.register(app)
        log.info("Đã đăng ký web blueprint")
    except Exception as e:
        log.error(f"web.register lỗi: {e}")

if api_mod and hasattr(api_mod, "register"):
    try:
        api_mod.register(app)
        log.info("Đã đăng ký api blueprint")
    except Exception as e:
        log.error(f"api.register lỗi: {e}")

# ============================================================
# ROUTE CƠ BẢN - LUÔN HOẠT ĐỘNG DÙ MODULE LỖI
# ============================================================

@app.route("/")
def index():
    return "Key Server OK"

@app.route("/ping")
def ping():
    return "pong"

@app.route("/health")
def health():
    status = {
        "ok": True,
        "service": "key-server",
        "time": int(time.time()),
        "port": os.environ.get("PORT", "10000"),
        "python": sys.version.split()[0],
        "modules": _modules_status,
        "bot": _bot_status(),
    }
    return jsonify(status)

@app.route("/status")
def status_page():
    rows = []
    for name, st in _modules_status.items():
        cls = "ok" if st == "OK" else "err"
        rows.append(f"<tr><td>{name}</td><td class='{cls}'>{st}</td></tr>")
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <title>Status</title>
    <style>
        body{{font-family:monospace;background:#0d1117;color:#c9d1d9;padding:20px}}
        table{{border-collapse:collapse;width:100%;max-width:600px}}
        td,th{{border:1px solid #30363d;padding:8px}}
        th{{background:#21262d;color:#58a6ff}}
        .ok{{color:#3fb950}} .err{{color:#f85149}}
        h1{{color:#58a6ff}}
    </style></head><body>
    <h1>KEY SERVER STATUS</h1>
    <p>Port: <b>{os.environ.get('PORT', '10000')}</b></p>
    <p>Python: <b>{sys.version.split()[0]}</b></p>
    <p>Bot: <b>{_bot_status()}</b></p>
    <table><tr><th>Module</th><th>Trạng thái</th></tr>
    {''.join(rows)}
    </table></body></html>"""
    return html

# ============================================================
# BOT TRONG THREAD PHỤ
# ============================================================

_bot_state = {
    "started": False,
    "running": False,
    "error": None,
    "started_at": None,
    "updates": 0,
}
_bot_lock = threading.Lock()

def _bot_status():
    if not _bot_state["started"]:
        return "chưa khởi động"
    if _bot_state["error"]:
        return f"lỗi: {_bot_state['error']}"
    if _bot_state["running"]:
        return "đang chạy"
    return "đã dừng"

def _start_bot_worker():
    if not bot_mod:
        _bot_state["error"] = "module bot không import được"
        log.warning("Bot không khởi động: module bot lỗi")
        return

    _bot_state["started"] = True
    _bot_state["started_at"] = int(time.time())

    try:
        if hasattr(bot_mod, "start_workers"):
            bot_mod.start_workers()
            log.info("Đã khởi động bot workers")

        use_webhook = os.environ.get("USE_WEBHOOK", "false").lower() == "true"

        if use_webhook:
            if hasattr(bot_mod, "set_webhook_from_env"):
                bot_mod.set_webhook_from_env()
            log.info("Bot chạy chế độ webhook")
            _bot_state["running"] = True
            while True:
                time.sleep(3600)
        else:
            if hasattr(bot_mod, "polling_worker"):
                log.info("Bot bắt đầu polling")
                _bot_state["running"] = True
                bot_mod.polling_worker()
            else:
                log.warning("bot.py không có hàm polling_worker")
                _bot_state["error"] = "thiếu hàm polling_worker"
    except Exception as e:
        _bot_state["error"] = str(e)
        _bot_state["running"] = False
        log.error(f"Bot worker lỗi: {e}")
        log.error(traceback.format_exc())

def start_bot_once():
    with _bot_lock:
        if _bot_state["started"]:
            return
    threading.Thread(target=_start_bot_worker, daemon=True, name="bot-worker").start()

# Chỉ chạy bot nếu có BOT_TOKEN và ENABLE_BOT=true
if (
    os.environ.get("BOT_TOKEN")
    and os.environ.get("ENABLE_BOT", "true").lower() == "true"
    and bot_mod
):
    log.info("Khởi động bot trong thread phụ...")
    start_bot_once()
elif not os.environ.get("BOT_TOKEN"):
    log.warning("Không có BOT_TOKEN, bot không khởi động")

# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api"):
        return jsonify({"ok": False, "error": "not_found"}), 404
    return "404 Not Found", 404

@app.errorhandler(500)
def server_error(e):
    log.error(f"500: {e}")
    return jsonify({"ok": False, "error": "internal_error"}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    log.error(f"Unhandled exception: {e}")
    log.error(traceback.format_exc())
    return jsonify({"ok": False, "error": str(e)}), 500

# ============================================================
# GRACEFUL SHUTDOWN
# ============================================================

def _shutdown_handler(signum, frame):
    log.info(f"Nhận signal {signum}, đang dừng...")
    _bot_state["running"] = False

signal.signal(signal.SIGTERM, _shutdown_handler)
signal.signal(signal.SIGINT, _shutdown_handler)

# ============================================================
# MAIN - CHỈ CHẠY KHI GỌI TRỰC TIẾP
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    host = os.environ.get("HOST", "0.0.0.0")
    log.info(f"Flask chạy trên {host}:{port}")
    print(f"[APP] Sẵn sàng nhận request tại http://{host}:{port}", flush=True)
    app.run(host=host, port=port, threaded=True, use_reloader=False, debug=False)
