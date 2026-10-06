# Sinh cấu hình cho engine con nhện phía client
import json
import random
from datetime import datetime


# Danh sách nhãn mặc định theo studio.prompt
DEFAULT_LABELS = [
    "staff hired", "source packet", "clear object", "drafts",
    "role", "objective", "ship", "one", "manual run", "start",
    "result", "repeat", "use only", "actually", "provided",
    "brand", "fact sheet", "transcript", "saved", "feedback",
    "next", "approve", "publishing", "external", "context",
    "researcher", "writer", "producer", "editor", "publisher",
]

# Bảng màu cho từng node
DEFAULT_COLORS = [
    "#ff5a8a", "#ff8a5a", "#ffd75a", "#a8ff5a", "#5affa8",
    "#5ad7ff", "#5a8aff", "#a85aff", "#ff5ad7", "#ff5a5a",
]


def build_node_config(labels=None, colors=None) -> dict:
    # Tạo cấu hình node cho client
    labels = labels or DEFAULT_LABELS
    colors = colors or DEFAULT_COLORS

    nodes = []
    for i, label in enumerate(labels):
        nodes.append({
            "id": i,
            "label": label,
            "color": colors[i % len(colors)],
            "radius": 30,
            "delay": random.randint(15, 30),
        })

    return {
        "count": len(nodes),
        "nodes": nodes,
        "generated_at": datetime.utcnow().isoformat(),
    }


def build_spider_config() -> dict:
    # Tạo cấu hình nhện chính và nhện con
    return {
        "main": {
            "size": 2.4,
            "color": "#c060ff",
            "speed": 0.3,
            "maxSpeed": 8,
            "trailLength": 30,
            "glow": True,
        },
        "babies": {
            "count": 4,
            "size": 1.1,
            "speed": 0.5,
            "maxSpeed": 3,
        },
        "particles": {
            "burst": 12,
            "life": 1.0,
            "decay": 0.02,
        },
        "escape": {
            "radius": 120,
            "force": 0.5,
        },
    }


def get_spider_payload() -> dict:
    # Trả về toàn bộ payload cho client
    return {
        "nodes": build_node_config(),
        "spider": build_spider_config(),
        "version": "2.0.0",
    }


def to_json(payload: dict) -> str:
    # Chuyển payload thành chuỗi JSON an toàn
    return json.dumps(payload, ensure_ascii=False)
