# app.py - Test port binding
import os
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "OK"

@app.route("/health")
def health():
    return {"ok": True}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"[APP] Chạy Flask trên 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)
