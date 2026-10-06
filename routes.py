# Đăng ký các route giao diện cho ứng dụng Flask
import logging
from datetime import datetime
from flask import render_template, redirect, url_for, request

logger = logging.getLogger(__name__)


def register_routes(app) -> None:
    # Route trang chính
    @app.route("/")
    def index():
        # Ghi log truy cập
        logger.info("Truy cập trang chính từ %s", request.remote_addr)

        # Trả về trang chính với dữ liệu thời gian
        return render_template(
            "index.html",
            now=datetime.utcnow(),
            locale=app.config.get("DEFAULT_LOCALE", "vi"),
            timezone=app.config.get("TIMEZONE", "Asia/Ho_Chi_Minh"),
        )

    # Route giới thiệu
    @app.route("/about")
    def about():
        # Trả về trang giới thiệu
        return render_template(
            "about.html",
            now=datetime.utcnow(),
        )

    # Route liên hệ
    @app.route("/contact")
    def contact():
        # Trả về trang liên hệ
        return render_template(
            "contact.html",
            now=datetime.utcnow(),
        )

    # Route chuyển hướng trang chủ
    @app.route("/home")
    def home():
        # Chuyển hướng về trang chính
        return redirect(url_for("index"))

    # Route favicon tránh lỗi 404
    @app.route("/favicon.ico")
    def favicon():
        # Trả về không nội dung
        return "", 204

    # Route kiểm tra tình trạng
    @app.route("/status")
    def status():
        # Trả về trạng thái hoạt động
        return {
            "status": "running",
            "time": datetime.utcnow().isoformat(),
        }

    # Route bắt mọi đường dẫn không tồn tại
    @app.route("/<path:path>")
    def catch_all(path):
        # Ghi log đường dẫn không tồn tại
        logger.warning("Đường dẫn không tồn tại: %s", path)

        # Trả về trang lỗi 404
        return render_template(
            "error.html",
            code=404,
            message="Không tìm thấy trang",
        ), 404
