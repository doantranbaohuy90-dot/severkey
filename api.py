# Đăng ký các route API
import logging
from datetime import datetime
from flask import jsonify, request

from spider_engine import get_spider_payload

logger = logging.getLogger(__name__)


def register_api(app) -> None:

    # Endpoint kiểm tra tình trạng
    @app.route("/api/health")
    def health():
        # Trả về trạng thái hoạt động
        return jsonify({
            "status": "ok",
            "time": datetime.utcnow().isoformat(),
        })

    # Endpoint cấu hình nhện
    @app.route("/api/spider/config")
    def spider_config():
        # Trả về cấu hình đầy đủ cho client
        return jsonify(get_spider_payload())

    # Endpoint danh sách node
    @app.route("/api/spider/nodes")
    def spider_nodes():
        # Trả về danh sách node
        payload = get_spider_payload()
        return jsonify(payload["nodes"])

    # Endpoint lấy nhãn tùy chỉnh từ yêu cầu
    @app.route("/api/spider/nodes", methods=["POST"])
    def spider_nodes_custom():
        # Đọc dữ liệu JSON
        data = request.get_json(silent=True)

        # Kiểm tra dữ liệu đầu vào
        if not isinstance(data, dict):
            return jsonify({"error": "Dữ liệu không hợp lệ"}), 400

        # Lấy danh sách nhãn
        labels = data.get("labels")

        # Kiểm tra kiểu dữ liệu
        if not isinstance(labels, list):
            return jsonify({"error": "Danh sách nhãn không hợp lệ"}), 400

        # Giới hạn số lượng
        if len(labels) > 60:
            return jsonify({"error": "Quá nhiều nhãn"}), 400

        # Lọc nhãn hợp lệ
        clean = [str(x)[:64] for x in labels if isinstance(x, str)]

        # Trả về cấu hình mới
        from spider_engine import build_node_config
        return jsonify(build_node_config(clean))
