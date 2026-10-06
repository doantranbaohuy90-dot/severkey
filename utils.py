# Các hàm tiện ích dùng chung cho ứng dụng Flask
import os
import re
import json
import html
import hashlib
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Biểu thức chính quy kiểm tra ký tự điều khiển
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

# Biểu thức chính quy kiểm tra tên trường hợp lệ
FIELD_NAME_RE = re.compile(r"^[a-zA-Z0-9_]{1,32}$")

# Biểu thức chính quy kiểm tra số điện thoại
PHONE_RE = re.compile(r"^\+?\d{9,15}$")

# Biểu thức chính quy kiểm tra email
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def now_utc() -> datetime:
    # Trả về thời gian hiện tại theo UTC
    return datetime.now(timezone.utc)


def now_iso() -> str:
    # Trả về thời gian hiện tại dạng chuỗi ISO
    return now_utc().isoformat()


def now_local(tz_name: str = "Asia/Ho_Chi_Minh") -> datetime:
    # Trả về thời gian hiện tại theo múi giờ chỉ định
    offset = timedelta(hours=7)
    return now_utc() + offset


def format_date(dt: datetime) -> str:
    # Định dạng ngày tháng theo kiểu hiển thị
    days = [
        "MONDAY", "TUESDAY", "WEDNESDAY",
        "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY",
    ]
    months = [
        "JANUARY", "FEBRUARY", "MARCH", "APRIL",
        "MAY", "JUNE", "JULY", "AUGUST",
        "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
    ]
    return f"{days[dt.weekday()]} · {months[dt.month - 1]} {dt.day}, {dt.year}"


def format_time(dt: datetime) -> dict:
    # Trả về giờ, phút, giây, AM/PM
    h = dt.hour
    ampm = "PM" if h >= 12 else "AM"
    h12 = h % 12
    if h12 == 0:
        h12 = 12
    return {
        "hour": f"{h12:02d}",
        "minute": f"{dt.minute:02d}",
        "second": f"{dt.second:02d}",
        "ampm": ampm,
    }


def sanitize(text: str) -> str:
    # Loại bỏ ký tự điều khiển khỏi chuỗi
    if not isinstance(text, str):
        return ""
    return CONTROL_RE.sub("", text)


def escape_html(text: str) -> str:
    # Thoát ký tự HTML để chống XSS
    if not isinstance(text, str):
        return ""
    return html.escape(text, quote=True)


def is_valid_field_name(name: str) -> bool:
    # Kiểm tra tên trường hợp lệ
    if not isinstance(name, str):
        return False
    return bool(FIELD_NAME_RE.match(name))


def is_valid_field_value(value: str, max_len: int = 500) -> bool:
    # Kiểm tra giá trị trường hợp lệ
    if not isinstance(value, str):
        return False
    return 1 <= len(value) <= max_len


def is_valid_phone(value: str) -> bool:
    # Kiểm tra số điện thoại hợp lệ
    if not isinstance(value, str):
        return False
    return bool(PHONE_RE.match(value))


def is_valid_email(value: str) -> bool:
    # Kiểm tra email hợp lệ
    if not isinstance(value, str):
        return False
    return bool(EMAIL_RE.match(value))


def to_json(data) -> str:
    # Chuyển đối tượng thành chuỗi JSON
    return json.dumps(data, ensure_ascii=False)


def from_json(raw: str, fallback=None) -> dict:
    # Chuyển chuỗi JSON thành đối tượng
    if fallback is None:
        fallback = {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return fallback


def hash_id(value: str, length: int = 16) -> str:
    # Băm một chuỗi thành mã định danh
    if not isinstance(value, str):
        value = str(value)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def truncate(text: str, limit: int = 100) -> str:
    # Cắt ngắn chuỗi theo giới hạn
    if not isinstance(text, str):
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def safe_join(base: str, *paths: str) -> str:
    # Nối đường dẫn an toàn chống path traversal
    base = os.path.abspath(base)
    target = os.path.abspath(os.path.join(base, *paths))
    if not target.startswith(base):
        raise ValueError("Đường dẫn không hợp lệ")
    return target


def ensure_dir(path: str) -> None:
    # Tạo thư mục nếu chưa tồn tại
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
        logger.info("Đã tạo thư mục: %s", path)


def chunk_list(items: list, size: int = 10) -> list:
    # Chia danh sách thành các nhóm nhỏ
    if size <= 0:
        return [items]
    return [items[i:i + size] for i in range(0, len(items), size)]


def parse_bool(value) -> bool:
    # Chuyển giá trị thành kiểu boolean
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def parse_int(value, fallback: int = 0) -> int:
    # Chuyển giá trị thành kiểu số nguyên
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def get_env(key: str, fallback: str = "") -> str:
    # Đọc biến môi trường với giá trị mặc định
    return os.environ.get(key, fallback)


def mask_secret(value: str, visible: int = 4) -> str:
    # Che khuất một phần chuỗi bí mật
    if not isinstance(value, str) or len(value) <= visible:
        return "*" * len(value) if isinstance(value, str) else ""
    return value[:visible] + "*" * (len(value) - visible)
