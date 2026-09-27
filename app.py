# app.py - Entry point cho Render Web Service
# Tác giả: MADE BY Bao Huy

import os
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Key Server OK"

@app.route("/health")
def health():
    return {"ok": True, "port": os.environ.get("PORT", "chưa set")}

@app.route("/ping")
def ping():
    return "pong"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"[APP] Flask chạy trên 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
