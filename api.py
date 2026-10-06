# Đăng ký các route API cho ứng dụng Flask
import logging
from datetime import datetime
from flask import jsonify, request

from spider_engine import (
    get_spider_payload,
    build_node_config,
    build_spider_config,
)

logger = logging.getLogger(__name__)

# Giới hạn số lượng nhãn tùy chỉnh
MAX_LABELS = 60

# Độ dài tối đa của mỗi nhãn
MAX_LABEL_LENGTH = 64


def _json_error(message: str, code: int = 400):
    # Trả về lỗi JSON theo định dạng thống nhất
    return jsonify({
        "ok": False,
        "error": message,
        "code": code,
        "time": datetime.utcnow().isoformat(),
    }), code


def _json_ok(payload: dict, code: int = 200):
    # Trả về thành công JSON theo định dạng thống nhất
    return jsonify({
        "ok": True,
        "data": payload,
        "time": datetime.utcnow().isoformat(),
    }), code


def register_api(app) -> None:

    # ======================================================================
    # ENDPOINT KIỂM TRA TÌNH TRẠNG
    # ======================================================================
    @app.route("/api/health")
    def health():
        # Trả về trạng thái hoạt động
        return jsonify({
            "status": "ok",
            "time": datetime.utcnow().isoformat(),
            "version": "1.0.0",
        })

    # ======================================================================
    # ENDPOINT PHIÊN BẢN
    # ======================================================================
    @app.route("/api/version")
    def version():
        # Trả về phiên bản ứng dụng
        return jsonify({
            "name": "ho-so-cua-toi",
            "version": "1.0.0",
            "build": "2026.10.06",
        })

    # ======================================================================
    # ENDPOINT THÔNG TIN CHỦ SỞ HỮU
    # ======================================================================
    @app.route("/api/owner")
    def owner():
        # Trả về thông tin chủ sở hữu
        return jsonify({
            "name": "Doãn Trần Bảo Huy",
            "telegram": "https://t.me/baohuyno1",
            "zalo": "https://zalo.me/0347635805",
            "phone": "0347635805",
            "role": "Seller & Website, Bot Developer",
        })

    # ======================================================================
    # ENDPOINT CẤU HÌNH NHỆN
    # ======================================================================
    @app.route("/api/spider/config")
    def spider_config():
        # Lấy payload cấu hình đầy đủ
        payload = get_spider_payload()

        # Trả về cấu hình
        return jsonify(payload)

    # ======================================================================
    # ENDPOINT CẤU HÌNH NHỆN CHÍNH
    # ======================================================================
    @app.route("/api/spider/main")
    def spider_main():
        # Trả về cấu hình nhện chính
        return jsonify(build_spider_config())

    # ======================================================================
    # ENDPOINT DANH SÁCH NODE (GET)
    # ======================================================================
    @app.route("/api/spider/nodes", methods=["GET"])
    def spider_nodes():
        # Lấy payload và trả về danh sách node
        payload = get_spider_payload()
        return jsonify(payload.get("nodes", {}))

    # ======================================================================
    # ENDPOINT DANH SÁCH NODE TÙY CHỈNH (POST)
    # ======================================================================
    @app.route("/api/spider/nodes", methods=["POST"])
    def spider_nodes_custom():
        # Đọc dữ liệu JSON từ yêu cầu
        data = request.get_json(silent=True)

        # Kiểm tra dữ liệu đầu vào
        if not isinstance(data, dict):
            return _json_error("Dữ liệu không hợp lệ")

        # Lấy danh sách nhãn
        labels = data.get("labels")

        # Kiểm tra kiểu dữ liệu
        if not isinstance(labels, list):
            return _json_error("Danh sách nhãn không hợp lệ")

        # Giới hạn số lượng nhãn
        if len(labels) > MAX_LABELS:
            return _json_error(f"Quá nhiều nhãn, tối đa {MAX_LABELS}")

        # Lọc nhãn hợp lệ và cắt độ dài
        clean = []
        for item in labels:
            if isinstance(item, str):
                text = item.strip()[:MAX_LABEL_LENGTH]
                if text:
                    clean.append(text)

        # Kiểm tra sau khi lọc
        if not clean:
            return _json_error("Không có nhãn hợp lệ")

        # Trả về cấu hình mới
        return jsonify(build_node_config(clean))

    # ======================================================================
    # ENDPOINT NHẬN HỒ SƠ
    # ======================================================================
    @app.route("/api/profile", methods=["POST"])
    def save_profile():
        # Đọc dữ liệu JSON từ yêu cầu
        payload = request.get_json(silent=True)

        # Kiểm tra dữ liệu đầu vào
        if not isinstance(payload, dict):
            return _json_error("Dữ liệu không hợp lệ")

        # Giới hạn số trường
        max_fields = app.config.get("MAX_PROFILE_FIELDS", 20)
        if len(payload) > max_fields:
            return _json_error(f"Vượt quá {max_fields} trường cho phép")

        # Ghi log dữ liệu nhận được
        logger.info("Nhận hồ sơ từ %s: %s", request.remote_addr, payload)

        # Trả về kết quả
        return jsonify({
            "status": "saved",
            "received": payload,
            "time": datetime.utcnow().isoformat(),
        })

    # ======================================================================
    # ENDPOINT LẤY HỒ SƠ THEO MÃ
    # ======================================================================
    @app.route("/api/profile/<int:user_id>")
    def get_profile(user_id: int):
        # Kiểm tra mã người dùng hợp lệ
        if user_id <= 0:
            return _json_error("Mã không hợp lệ")

        # Trả về dữ liệu hồ sơ mẫu
        return jsonify({
            "user_id": user_id,
            "data": {
                "name": "Doãn Trần Bảo Huy",
                "role": "Developer",
            },
            "time": datetime.utcnow().isoformat(),
        })

    # ======================================================================
    # XỬ LÝ LỖI API
    # ======================================================================
    @app.errorhandler(404)
    def api_not_found(error):
        # Nếu đường dẫn thuộc API, trả về JSON
        if request.path.startswith("/api/"):
            return _json_error("Không tìm thấy endpoint", 404)

        # Ngược lại, để handler giao diện xử lý
        return error

    @app.errorhandler(405)
    def api_method_not_allowed(error):
        # Nếu đường dẫn thuộc API, trả về JSON
        if request.path.startswith("/api/"):
            return _json_error("Phương thức không được phép", 405)

        # Ngược lại, để handler giao diện xử lý
        return error

    @app.errorhandler(500)
    def api_server_error(error):
        # Ghi log lỗi máy chủ
        logger.exception("Lỗi máy chủ API: %s", error)

        # Nếu đường dẫn thuộc API, trả về JSON
        if request.path.startswith("/api/"):
            return _json_error("Lỗi máy chủ nội bộ", 500)

        # Ngược lại, để handler giao diện xử lý
        return error
