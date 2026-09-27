from flask import Flask
import web
import api

app = Flask(__name__)

# Đăng ký web trước để route "/api" (giao diện) ưu tiên
web.register(app)
api.register(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
