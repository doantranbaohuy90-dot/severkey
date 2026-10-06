# Điểm khởi chạy chính của ứng dụng Flask
import os
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv

# Nạp biến môi trường từ tệp .env
load_dotenv()

# Khởi tạo logger
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    # Khởi tạo ứng dụng Flask với thư mục tĩnh và mẫu
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )

    # Cấu hình khóa bí mật
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")

    # Cấu hình chế độ debug
    app.config["DEBUG"] = os.environ.get("FLASK_DEBUG", "0") == "1"

    # Cấu hình JSON trả về tiếng Việt
    app.config["JSON_AS_ASCII"] = False
    app.config["JSON_SORT_KEYS"] = False

    # Cấu hình cache tệp tĩnh
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = int(
        os.environ.get("SEND_FILE_MAX_AGE_DEFAULT", "43200")
    )

    # Cấu hình giới hạn kích thước yêu cầu
    app.config["MAX_CONTENT_LENGTH"] = int(
        os.environ.get("MAX_CONTENT_LENGTH", str(16 * 1024 * 1024))
    )

    # Cấu hình ngôn ngữ mặc định
    app.config["DEFAULT_LOCALE"] = os.environ.get("DEFAULT_LOCALE", "vi")

    # Cấu hình múi giờ
    app.config["TIMEZONE"] = os.environ.get("TIMEZONE", "Asia/Ho_Chi_Minh")

    # Đăng ký route giao diện
    register_routes(app)

    # Đăng ký route API
    register_api(app)

    # Đăng ký xử lý lỗi
    register_errors(app)

    # Ghi log khởi tạo
    logger.info("Ứng dụng đã khởi tạo")
    return app


def register_routes(app: Flask) -> None:
    # Route trang chính
    @app.route("/")
    def index():
        # Ghi log truy cập
        logger.info("Truy cập trang chính từ %s", request.remote_addr)

        # Trả về trang chính với thời gian hiện tại
        return render_template(
            "index.html",
            now=datetime.utcnow(),
            locale=app.config["DEFAULT_LOCALE"],
            timezone=app.config["TIMEZONE"],
        )

    # Route trang con nhện chạy trên code
    @app.route("/spider")
    def spider():
        # Ghi log truy cập
        logger.info("Truy cập trang con nhện từ %s", request.remote_addr)

        # Trả về trang con nhện
        return render_template(
            "spider.html",
            now=datetime.utcnow(),
        )

    # Route favicon tránh lỗi 404
    @app.route("/favicon.ico")
    def favicon():
        # Trả về 204 không nội dung
        return "", 204

    # Route kiểm tra tình trạng
    @app.route("/status")
    def status():
        # Trả về trạng thái hoạt động
        return jsonify({
            "status": "running",
            "time": datetime.utcnow().isoformat(),
        })


def register_api(app: Flask) -> None:
    # Endpoint kiểm tra tình trạng máy chủ
    @app.route("/api/health")
    def health():
        return jsonify({
            "status": "ok",
            "time": datetime.utcnow().isoformat(),
        })

    # Endpoint trả về phiên bản ứng dụng
    @app.route("/api/version")
    def version():
        return jsonify({
            "name": "ho-so-cua-toi",
            "version": "1.0.0",
            "build": "2026.10.06",
        })

    # Endpoint trả về thông tin chủ sở hữu
    @app.route("/api/owner")
    def owner():
        return jsonify({
            "name": "Doãn Trần Bảo Huy",
            "telegram": "https://t.me/baohuyno1",
            "zalo": "https://zalo.me/0347635805",
            "phone": "0347635805",
            "role": "Seller & Website, Bot Developer",
        })

    # Endpoint lấy danh sách dự án
    @app.route("/api/projects")
    def projects():
        # Danh sách dự án mẫu
        items = [
            {"id": 1, "name": "Hồ sơ cá nhân", "status": "done"},
            {"id": 2, "name": "Bot Telegram", "status": "wip"},
            {"id": 3, "name": "Web API", "status": "done"},
            {"id": 4, "name": "Con nhện chạy", "status": "done"},
        ]

        # Trả về danh sách dự án
        return jsonify({
            "count": len(items),
            "items": items,
        })

    # Endpoint nhận dữ liệu hồ sơ
    @app.route("/api/profile", methods=["POST"])
    def save_profile():
        # Đọc dữ liệu JSON từ yêu cầu
        payload = request.get_json(silent=True)

        # Kiểm tra dữ liệu đầu vào
        if not isinstance(payload, dict):
            return jsonify({"error": "Dữ liệu không hợp lệ"}), 400

        # Giới hạn số trường
        if len(payload) > 20:
            return jsonify({"error": "Vượt quá số trường cho phép"}), 400

        # Ghi log dữ liệu nhận được
        logger.info("Nhận hồ sơ từ %s: %s", request.remote_addr, payload)

        # Trả về kết quả
        return jsonify({
            "status": "saved",
            "received": payload,
            "time": datetime.utcnow().isoformat(),
        })

    # Endpoint lấy dữ liệu hồ sơ theo mã
    @app.route("/api/profile/<int:user_id>")
    def get_profile(user_id: int):
        # Kiểm tra mã người dùng hợp lệ
        if user_id <= 0:
            return jsonify({"error": "Mã không hợp lệ"}), 400

        # Trả về dữ liệu hồ sơ mẫu
        return jsonify({
            "user_id": user_id,
            "data": {
                "name": "Doãn Trần Bảo Huy",
                "role": "Developer",
            },
            "time": datetime.utcnow().isoformat(),
        })


def register_errors(app: Flask) -> None:
    # Xử lý lỗi 404
    @app.errorhandler(404)
    def not_found(error):
        # Kiểm tra yêu cầu thuộc API
        if request.path.startswith("/api/"):
            return jsonify({"error": "Không tìm thấy endpoint"}), 404

        return render_template(
            "error.html",
            code=404,
            message="Không tìm thấy trang",
        ), 404

    # Xử lý lỗi 500
    @app.errorhandler(500)
    def server_error(error):
        # Ghi log lỗi
        logger.exception("Lỗi máy chủ: %s", error)

        # Kiểm tra yêu cầu thuộc API
        if request.path.startswith("/api/"):
            return jsonify({"error": "Lỗi máy chủ nội bộ"}), 500

        return render_template(
            "error.html",
            code=500,
            message="Lỗi máy chủ nội bộ",
        ), 500

    # Xử lý lỗi 405
    @app.errorhandler(405)
    def method_not_allowed(error):
        return render_template(
            "error.html",
            code=405,
            message="Phương thức không được phép",
        ), 405

    # Xử lý lỗi 403
    @app.errorhandler(403)
    def forbidden(error):
        return render_template(
            "error.html",
            code=403,
            message="Không có quyền truy cập",
        ), 403


# Khởi tạo ứng dụng toàn cục cho gunicorn
app = create_app()


if __name__ == "__main__":
    # Cổng do Render cung cấp qua biến môi trường
    port = int(os.environ.get("PORT", 5000))

    # Chạy máy chủ phát triển
    app.run(host="0.0.0.0", port=port)
