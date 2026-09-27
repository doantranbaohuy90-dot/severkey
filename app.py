# app.py - Entry point cho Render Web Service
# Tác giả: MADE BY Bao Huy
# Chạy web + API + bot trong cùng process

import os
import threading
from flask import Flask, jsonify

app = Flask(__name__)

# ---------------- ĐĂNG KÝ BLUEPRINT ----------------

try:
    import web
    web.register(app)
    print("[APP] Đã đăng ký web blueprint")
except Exception as e:
    print(f"[APP] web blueprint lỗi: {e}")

try:
    import api
    api.register(app)
    print("[APP] Đã đăng ký api blueprint")
except Exception as e:
    print(f"[APP] api blueprint lỗi: {e}")

# ---------------- ROUTE CƠ BẢN ----------------

@app.route("/")
def index():
    return "Key Server OK"

@app.route("/health")
def health():
    import time
    return jsonify({
        "ok": True,
        "service": "key-server",
        "port": os.environ.get("PORT", "10000"),
        "time": int(time.time()),
    })

@app.route("/ping")
def ping():
    return "pong"

# ---------------- BOT TRONG THREAD PHỤ ----------------

_bot_started = False
_bot_lock = threading.Lock()

def _start_bot():
    try:
        import bot
        bot.start_workers()
        use_webhook = os.environ.get("USE_WEBHOOK", "false").lower() == "true"
        if use_webhook:
            bot.set_webhook_from_env()
            print("[APP] Bot chạy webhook.")
            while True:
                import time
                time.sleep(3600)
        else:
            print("[APP] Bot bắt đầu polling.")
            bot.polling_worker()
    except Exception as e:
        import traceback
        print(f"[APP] Bot worker lỗi: {e}")
        traceback.print_exc()

def start_bot_once():
    global _bot_started
    with _bot_lock:
        if _bot_started:
            return
        _bot_started = True
    threading.Thread(target=_start_bot, daemon=True).start()

# Chỉ chạy bot 1 lần khi process khởi động
if os.environ.get("ENABLE_BOT", "true").lower() == "true":
    start_bot_once()

# ---------------- MAIN ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"[APP] Flask chạy trên 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)
