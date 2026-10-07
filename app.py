# Điểm khởi chạy chính của ứng dụng Flask
import os
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv

# Nạp biến môi trường
load_dotenv()

# Cấu hình logger
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ==========================================================================
# ĐỒ THỊ MẪU CHO THUẬT TOÁN BFS
# ==========================================================================
BFS_GRAPH = {
    "A": ["B", "C"],
    "B": ["A", "D", "E"],
    "C": ["A", "F"],
    "D": ["B"],
    "E": ["B", "F"],
    "F": ["C", "E", "G"],
    "G": ["F"],
}


def create_app() -> Flask:
    # Khởi tạo ứng dụng Flask
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )

    # Cấu hình cơ bản
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
    app.config["DEBUG"] = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.config["JSON_AS_ASCII"] = False
    app.config["JSON_SORT_KEYS"] = False
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    app.config["DEFAULT_LOCALE"] = os.environ.get("DEFAULT_LOCALE", "vi")
    app.config["TIMEZONE"] = os.environ.get("TIMEZONE", "Asia/Ho_Chi_Minh")
    app.config["MAX_PROFILE_FIELDS"] = int(os.environ.get("MAX_PROFILE_FIELDS", "20"))

    # Chặn cache HTML
    @app.after_request
    def no_cache(response):
        if response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    # Đăng ký route
    register_routes(app)
    register_api(app)
    register_errors(app)

    logger.info("Ứng dụng đã khởi tạo")
    return app


# ==========================================================================
# ROUTE GIAO DIỆN
# ==========================================================================
def register_routes(app: Flask) -> None:

    @app.route("/")
    def index():
        # Trang chính
        logger.info("Trang chính từ %s", request.remote_addr)
        return render_template(
            "index.html",
            now=datetime.utcnow(),
            locale=app.config["DEFAULT_LOCALE"],
            timezone=app.config["TIMEZONE"],
        )

    @app.route("/spider")
    def spider():
        # Trang con nhện
        logger.info("Trang con nhện từ %s", request.remote_addr)
        return render_template("spider.html", now=datetime.utcnow())

    @app.route("/bfs")
    def bfs():
        # Trang mô phỏng thuật toán BFS
        logger.info("Trang BFS từ %s", request.remote_addr)
        return render_template(
            "bfs.html",
            graph=BFS_GRAPH,
            now=datetime.utcnow(),
        )

    @app.route("/favicon.ico")
    def favicon():
        # Tránh lỗi 404 favicon
        return "", 204

    @app.route("/status")
    def status():
        # Trạng thái hoạt động
        return jsonify({
            "status": "running",
            "time": datetime.utcnow().isoformat(),
        })


# ==========================================================================
# ROUTE API
# ==========================================================================
def register_api(app: Flask) -> None:

    @app.route("/api/health")
    def api_health():
        return jsonify({
            "status": "ok",
            "time": datetime.utcnow().isoformat(),
            "version": "1.0.0",
        })

    @app.route("/api/version")
    def api_version():
        return jsonify({
            "name": "ho-so-cua-toi",
            "version": "1.0.0",
            "build": "2026.10.07",
        })

    @app.route("/api/owner")
    def api_owner():
        return jsonify({
            "name": "Doãn Trần Bảo Huy",
            "telegram": "https://t.me/baohuyno1",
            "zalo": "https://zalo.me/0347635805",
            "phone": "0347635805",
            "email": "huydoan633@gmail.com",
            "role": "Seller & Website, Bot Developer",
        })

    @app.route("/api/projects")
    def api_projects():
        items = [
            {"id": 1, "name": "Hồ sơ cá nhân", "status": "done"},
            {"id": 2, "name": "Bot Telegram", "status": "wip"},
            {"id": 3, "name": "Web API", "status": "done"},
            {"id": 4, "name": "Con nhện chạy", "status": "done"},
            {"id": 5, "name": "Tìm đường BFS", "status": "done"},
        ]
        return jsonify({"count": len(items), "items": items})

    @app.route("/api/bfs/graph")
    def api_bfs_graph():
        # Trả về đồ thị BFS
        return jsonify({
            "graph": BFS_GRAPH,
            "nodes": list(BFS_GRAPH.keys()),
        })

    @app.route("/api/profile", methods=["POST"])
    def api_save_profile():
        payload = request.get_json(silent=True)

        if not isinstance(payload, dict):
            return jsonify({"error": "Dữ liệu không hợp lệ"}), 400

        max_fields = app.config["MAX_PROFILE_FIELDS"]
        if len(payload) > max_fields:
            return jsonify({"error": f"Vượt quá {max_fields} trường"}), 400

        logger.info("Nhận hồ sơ từ %s", request.remote_addr)
        return jsonify({
            "status": "saved",
            "received": payload,
            "time": datetime.utcnow().isoformat(),
        })

    @app.route("/api/profile/<int:user_id>")
    def api_get_profile(user_id: int):
        if user_id <= 0:
            return jsonify({"error": "Mã không hợp lệ"}), 400

        return jsonify({
            "user_id": user_id,
            "data": {
                "name": "Doãn Trần Bảo Huy",
                "role": "Developer",
            },
            "time": datetime.utcnow().isoformat(),
        })


# ==========================================================================
# XỬ LÝ LỖI
# ==========================================================================
def register_errors(app: Flask) -> None:

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Không tìm thấy endpoint"}), 404
        return render_template("error.html", code=404, message="Không tìm thấy trang"), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Phương thức không được phép"}), 405
        return render_template("error.html", code=405, message="Phương thức không được phép"), 405

    @app.errorhandler(403)
    def forbidden(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Không có quyền truy cập"}), 403
        return render_template("error.html", code=403, message="Không có quyền truy cập"), 403

    @app.errorhandler(500)
    def server_error(error):
        logger.exception("Lỗi máy chủ: %s", error)
        if request.path.startswith("/api/"):
            return jsonify({"error": "Lỗi máy chủ nội bộ"}), 500
        return render_template("error.html", code=500, message="Lỗi máy chủ nội bộ"), 500


# ==========================================================================
# KHỞI TẠO ỨNG DỤNG
# ==========================================================================
app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=app.config["DEBUG"])
