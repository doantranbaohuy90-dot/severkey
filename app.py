import os
import threading
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Key Server OK"

@app.route("/health")
def health():
    return {"ok": True}

def _start_bot():
    try:
        import bot
        bot.start_workers()
        if os.environ.get("USE_WEBHOOK", "false").lower() != "true":
            bot.polling_worker()
    except Exception as e:
        print(f"[APP] Bot worker lỗi: {e}")

# Chỉ chạy bot 1 lần khi process khởi động
_bot_started = False
def start_bot_once():
    global _bot_started
    if _bot_started:
        return
    _bot_started = True
    threading.Thread(target=_start_bot, daemon=True).start()

# Gọi khi import (gunicorn cũng chạy)
start_bot_once()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
