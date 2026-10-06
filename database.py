# ==========================================================================
# QUẢN LÝ CƠ SỞ DỮ LIỆU SQLITE
# Kết nối, khởi tạo bảng, truy vấn hồ sơ, dự án và nhật ký
# ==========================================================================

import os
import sqlite3
import logging
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Đường dẫn tệp cơ sở dữ liệu
DB_PATH = os.environ.get("DB_PATH", "ho_so.db")


# ==========================================================================
# KẾT NỐI CƠ SỞ DỮ LIỆU
# ==========================================================================
def get_connection() -> sqlite3.Connection:
    # Mở kết nối tới tệp SQLite
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Bật hỗ trợ khóa ngoại
    conn.execute("PRAGMA foreign_keys = ON")

    # Chế độ ghi an toàn
    conn.execute("PRAGMA journal_mode = WAL")

    return conn


@contextmanager
def connection():
    # Ngữ cảnh tự đóng kết nối
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ==========================================================================
# KHỞI TẠO BẢNG
# ==========================================================================
def init_db() -> None:
    # Tạo các bảng nếu chưa tồn tại
    with connection() as conn:
        # Bảng người dùng
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT UNIQUE,
                full_name   TEXT,
                telegram    TEXT,
                zalo        TEXT,
                phone       TEXT,
                email       TEXT,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                is_banned   INTEGER DEFAULT 0
            )
            """
        )

        # Bảng hồ sơ
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                user_id     INTEGER PRIMARY KEY,
                data        TEXT NOT NULL,
                updated_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            )
            """
        )

        # Bảng cài đặt
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                user_id         INTEGER PRIMARY KEY,
                language        TEXT DEFAULT 'vi',
                notifications   INTEGER DEFAULT 1,
                theme           TEXT DEFAULT 'dark',
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            )
            """
        )

        # Bảng dự án
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                project_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                status      TEXT DEFAULT 'wip',
                url         TEXT,
                description TEXT,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Bảng nhật ký truy cập
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS access_log (
                log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ip          TEXT,
                path        TEXT,
                method      TEXT,
                user_agent  TEXT,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Bảng nhãn node con nhện
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spider_nodes (
                node_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                label       TEXT NOT NULL,
                color       TEXT,
                position    INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    logger.info("Cơ sở dữ liệu đã khởi tạo tại %s", DB_PATH)


# ==========================================================================
# NGƯỜI DÙNG
# ==========================================================================
def create_user(username: str, full_name: str = None, telegram: str = None,
                zalo: str = None, phone: str = None, email: str = None) -> int:
    # Tạo người dùng mới, trả về mã người dùng
    with connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO users (username, full_name, telegram, zalo, phone, email)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (username, full_name, telegram, zalo, phone, email),
        )
        user_id = cursor.lastrowid

    logger.info("Đã tạo người dùng: %s", username)
    return user_id


def get_user(username: str):
    # Lấy người dùng theo tên đăng nhập
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

    return dict(row) if row else None


def get_user_by_id(user_id: int):
    # Lấy người dùng theo mã
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()

    return dict(row) if row else None


def update_user(user_id: int, **fields) -> bool:
    # Cập nhật thông tin người dùng
    if not fields:
        return False

    # Chỉ cho phép các cột hợp lệ
    allowed = {
        "full_name", "telegram", "zalo", "phone", "email", "is_banned"
    }
    updates = {k: v for k, v in fields.items() if k in allowed}

    if not updates:
        return False

    # Tạo câu truy vấn động
    columns = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [datetime.utcnow().isoformat(), user_id]

    with connection() as conn:
        conn.execute(
            f"UPDATE users SET {columns}, updated_at = ? WHERE user_id = ?",
            values,
        )

    return True


def delete_user(user_id: int) -> bool:
    # Xóa người dùng và dữ liệu liên quan
    with connection() as conn:
        conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

    return True


# ==========================================================================
# HỒ SƠ
# ==========================================================================
def save_profile(user_id: int, data: dict) -> bool:
    # Lưu hoặc cập nhật hồ sơ
    import json
    payload = json.dumps(data, ensure_ascii=False)

    with connection() as conn:
        conn.execute(
            """
            INSERT INTO profiles (user_id, data, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                data = excluded.data,
                updated_at = excluded.updated_at
            """,
            (user_id, payload, datetime.utcnow().isoformat()),
        )

    return True


def get_profile(user_id: int) -> dict:
    # Lấy hồ sơ theo mã người dùng
    import json

    with connection() as conn:
        row = conn.execute(
            "SELECT data, updated_at FROM profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    if not row:
        return {}

    return {
        "data": json.loads(row["data"]),
        "updated_at": row["updated_at"],
    }


def delete_profile(user_id: int) -> bool:
    # Xóa hồ sơ
    with connection() as conn:
        conn.execute("DELETE FROM profiles WHERE user_id = ?", (user_id,))

    return True


# ==========================================================================
# CÀI ĐẶT
# ==========================================================================
def get_settings(user_id: int) -> dict:
    # Lấy cài đặt người dùng
    with connection() as conn:
        row = conn.execute(
            "SELECT language, notifications, theme FROM settings WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    if not row:
        return {"language": "vi", "notifications": 1, "theme": "dark"}

    return dict(row)


def save_settings(user_id: int, language: str = "vi",
                  notifications: int = 1, theme: str = "dark") -> bool:
    # Lưu cài đặt người dùng
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO settings (user_id, language, notifications, theme)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                language = excluded.language,
                notifications = excluded.notifications,
                theme = excluded.theme
            """,
            (user_id, language, notifications, theme),
        )

    return True


# ==========================================================================
# DỰ ÁN
# ==========================================================================
def add_project(name: str, status: str = "wip",
                url: str = None, description: str = None) -> int:
    # Thêm dự án mới
    with connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO projects (name, status, url, description)
            VALUES (?, ?, ?, ?)
            """,
            (name, status, url, description),
        )
        project_id = cursor.lastrowid

    return project_id


def get_projects() -> list:
    # Lấy danh sách dự án
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY project_id ASC"
        ).fetchall()

    return [dict(row) for row in rows]


def update_project(project_id: int, **fields) -> bool:
    # Cập nhật dự án
    if not fields:
        return False

    allowed = {"name", "status", "url", "description"}
    updates = {k: v for k, v in fields.items() if k in allowed}

    if not updates:
        return False

    columns = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [project_id]

    with connection() as conn:
        conn.execute(
            f"UPDATE projects SET {columns} WHERE project_id = ?",
            values,
        )

    return True


def delete_project(project_id: int) -> bool:
    # Xóa dự án
    with connection() as conn:
        conn.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))

    return True


# ==========================================================================
# NHẬT KÝ TRUY CẬP
# ==========================================================================
def log_access(ip: str, path: str, method: str, user_agent: str = None) -> int:
    # Ghi nhật ký truy cập
    with connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO access_log (ip, path, method, user_agent)
            VALUES (?, ?, ?, ?)
            """,
            (ip, path, method, user_agent),
        )
        log_id = cursor.lastrowid

    return log_id


def get_access_logs(limit: int = 100) -> list:
    # Lấy nhật ký truy cập gần đây
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM access_log ORDER BY log_id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def clear_access_logs() -> bool:
    # Xóa toàn bộ nhật ký truy cập
    with connection() as conn:
        conn.execute("DELETE FROM access_log")

    return True


# ==========================================================================
# NHÃN NODE CON NHỆN
# ==========================================================================
def save_spider_nodes(labels: list) -> int:
    # Lưu danh sách nhãn node
    with connection() as conn:
        conn.execute("DELETE FROM spider_nodes")

        for i, item in enumerate(labels):
            if isinstance(item, dict):
                label = item.get("label", "")
                color = item.get("color", "")
            else:
                label = str(item)
                color = ""

            conn.execute(
                """
                INSERT INTO spider_nodes (label, color, position)
                VALUES (?, ?, ?)
                """,
                (label, color, i),
            )

    return len(labels)


def get_spider_nodes() -> list:
    # Lấy danh sách nhãn node
    with connection() as conn:
        rows = conn.execute(
            "SELECT label, color, position FROM spider_nodes ORDER BY position ASC"
        ).fetchall()

    return [dict(row) for row in rows]


# ==========================================================================
# THỐNG KÊ
# ==========================================================================
def get_stats() -> dict:
    # Thống kê tổng quan
    with connection() as conn:
        users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        profiles = conn.execute("SELECT COUNT(*) AS c FROM profiles").fetchone()["c"]
        projects = conn.execute("SELECT COUNT(*) AS c FROM projects").fetchone()["c"]
        logs = conn.execute("SELECT COUNT(*) AS c FROM access_log").fetchone()["c"]

    return {
        "users": users,
        "profiles": profiles,
        "projects": projects,
        "access_logs": logs,
    }


# ==========================================================================
# KHỞI TẠO MẶC ĐỊNH
# ==========================================================================
def seed_default_data() -> None:
    # Thêm dữ liệu mẫu nếu bảng trống
    with connection() as conn:
        # Kiểm tra bảng dự án
        count = conn.execute("SELECT COUNT(*) AS c FROM projects").fetchone()["c"]

        if count == 0:
            default_projects = [
                ("Hồ sơ cá nhân", "done", None, "Trang hồ sơ cá nhân"),
                ("Bot Telegram", "wip", "https://t.me/baohuyno1", "Bot Telegram"),
                ("Web API", "done", None, "API cho ứng dụng"),
                ("Con nhện chạy", "done", None, "Hiệu ứng con nhện trên canvas"),
            ]

            for name, status, url, desc in default_projects:
                conn.execute(
                    """
                    INSERT INTO projects (name, status, url, description)
                    VALUES (?, ?, ?, ?)
                    """,
                    (name, status, url, desc),
                )

    logger.info("Dữ liệu mặc định đã được nạp")


# ==========================================================================
# CHẠY TRỰC TIẾP
# ==========================================================================
if __name__ == "__main__":
    # Khởi tạo cơ sở dữ liệu khi chạy trực tiếp
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    init_db()
    seed_default_data()
    print("Trạng thái:", get_stats())
