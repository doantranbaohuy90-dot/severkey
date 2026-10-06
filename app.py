# Điểm khởi chạy chính của ứng dụng Flask
import os
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify, request, abort
from dotenv import load_dotenv

# Nạp biến môi trường từ tệp .env
load_dotenv()

# Khởi tạo logger
logging.basicConfig(
    level=logging.INFO,
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

    # Đăng ký route giao diện
    register_routes(app)

    # Đăng ký route API
    register_api(app)

    # Đăng ký xử lý lỗi
    register_errors(app)

    logger.info("Ứng dụng đã khởi tạo")
    return app


def register_routes(app: Flask) -> None:
    # Route trang chính
    @app.route("/")
    def index():
        # Trả về trang chính với thời gian hiện tại
        return render_template(
            "index.html",
            now=datetime.utcnow(),
            locale=os.environ.get("DEFAULT_LOCALE", "vi"),
        )

    # Route favicon tránh lỗi 404
    @app.route("/favicon.ico")
    def favicon():
        # Trả về 204 không nội dung
        return "", 204


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
        })

    # Endpoint nhận dữ liệu hồ sơ
    @app.route("/api/profile", methods=["POST"])
    def save_profile():
        # Đọc dữ liệu JSON từ yêu cầu
        payload = request.get_json(silent=True)

        # Kiểm tra dữ liệu đầu vào
        if not isinstance(payload, dict):
            return jsonify({"error": "Dữ liệu không hợp lệ"}), 400

        # Ghi log dữ liệu nhận được
        logger.info("Nhận hồ sơ: %s", payload)

        # Trả về kết quả
        return jsonify({
            "status": "saved",
            "received": payload,
            "time": datetime.utcnow().isoformat(),
        })


def register_errors(app: Flask) -> None:
    # Xử lý lỗi 404
    @app.errorhandler(404)
    def not_found(error):
        return render_template(
            "error.html",
            code=404,
            message="Không tìm thấy trang",
        ), 404

    # Xử lý lỗi 500
    @app.errorhandler(500)
    def server_error(error):
        logger.exception("Lỗi máy chủ: %s", error)
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


# Khởi tạo ứng dụng toàn cục cho gunicorn
app = create_app()


if __name__ == "__main__":
    # Cổng do Render cung cấp qua biến môi trường
    port = int(os.environ.get("PORT", 5000))

    # Chạy máy chủ phát triển
    app.run(host="0.0.0.0", port=port)
