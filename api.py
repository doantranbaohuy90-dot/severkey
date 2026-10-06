# Đăng ký các route API cho ứng dụng Flask
import logging
from datetime import datetime
from flask import jsonify, request

logger = logging.getLogger(__name__)


def register_api(app) -> None:
    # Endpoint kiểm tra tình trạng máy chủ
    @app.route("/api/health")
    def health():
        # Trả về trạng thái hoạt động
        return jsonify({
            "status": "ok",
            "time": datetime.utcnow().isoformat(),
        })

    # Endpoint trả về phiên bản ứng dụng
    @app.route("/api/version")
    def version():
        # Trả về thông tin phiên bản
        return jsonify({
            "name": "ho-so-cua-toi",
            "version": "1.0.0",
            "build": "2026.10.06",
        })

    # Endpoint lấy danh sách dự án
    @app.route("/api/projects")
    def get_projects():
        # Danh sách dự án mẫu
        projects = [
            {"id": 1, "name": "Hồ sơ cá nhân", "status": "done"},
            {"id": 2, "name": "Bot Telegram", "status": "wip"},
            {"id": 3, "name": "Web API", "status": "done"},
        ]

        # Trả về danh sách dự án
        return jsonify({
            "count": len(projects),
            "items": projects,
        })

    # Endpoint nhận dữ liệu hồ sơ
    @app.route("/api/profile", methods=["POST"])
    def save_profile():
        # Đọc dữ liệu JSON từ yêu cầu
        payload = request.get_json(silent=True)

        # Kiểm tra dữ liệu đầu vào
        if not isinstance(payload, dict):
            return jsonify({"error": "Dữ liệu không hợp lệ"}), 400

        # Kiểm tra số trường tối đa
        max_fields = app.config.get("MAX_PROFILE_FIELDS", 20)
        if len(payload) > max_fields:
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
                "name": "Bao Huy",
                "role": "Developer",
            },
            "time": datetime.utcnow().isoformat(),
        })

    # Endpoint xử lý lỗi API
    @app.errorhandler(404)
    def api_not_found(error):
        # Kiểm tra yêu cầu thuộc API
        if request.path.startswith("/api/"):
            return jsonify({"error": "Không tìm thấy endpoint"}), 404

        # Trả về lỗi mặc định
        return error

    # Endpoint xử lý lỗi máy chủ API
    @app.errorhandler(500)
    def api_server_error(error):
        # Ghi log lỗi
        logger.exception("Lỗi máy chủ API: %s", error)

        # Kiểm tra yêu cầu thuộc API
        if request.path.startswith("/api/"):
            return jsonify({"error": "Lỗi máy chủ nội bộ"}), 500

        # Trả về lỗi mặc định
        return error
