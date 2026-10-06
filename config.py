# Cấu hình toàn cục của ứng dụng Flask
import os
from dotenv import load_dotenv

# Nạp biến môi trường từ tệp .env
load_dotenv()


class Config:
    # Khóa bí mật dùng cho session và CSRF
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    # Chế độ debug của Flask
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

    # Chế độ kiểm thử
    TESTING = os.environ.get("FLASK_TESTING", "0") == "1"

    # Ngôn ngữ mặc định
    DEFAULT_LOCALE = os.environ.get("DEFAULT_LOCALE", "vi")

    # Múi giờ mặc định
    TIMEZONE = os.environ.get("TIMEZONE", "Asia/Ho_Chi_Minh")

    # Thư mục chứa tệp tĩnh
    STATIC_FOLDER = "static"

    # Thư mục chứa mẫu HTML
    TEMPLATE_FOLDER = "templates"

    # Thời gian cache tệp tĩnh tính bằng giây
    SEND_FILE_MAX_AGE_DEFAULT = int(
        os.environ.get("SEND_FILE_MAX_AGE_DEFAULT", "43200")
    )

    # Kích thước tối đa của yêu cầu tính bằng byte
    MAX_CONTENT_LENGTH = int(
        os.environ.get("MAX_CONTENT_LENGTH", str(16 * 1024 * 1024))
    )

    # Giới hạn số trường hồ sơ
    MAX_PROFILE_FIELDS = int(os.environ.get("MAX_PROFILE_FIELDS", "20"))

    # Đường dẫn xuất dữ liệu
    EXPORT_DIR = os.environ.get("EXPORT_DIR", "exports")

    # Bật/tắt JSON trả về dạng ASCII
    JSON_AS_ASCII = False

    # Sắp xếp khóa JSON
    JSON_SORT_KEYS = False


class DevelopmentConfig(Config):
    # Cấu hình cho môi trường phát triển
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    # Cấu hình cho môi trường sản xuất
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    # Cấu hình cho môi trường kiểm thử
    DEBUG = False
    TESTING = True


# Bản đồ ánh xạ môi trường sang lớp cấu hình
CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name: str = None):
    # Lấy lớp cấu hình theo tên môi trường
    env = name or os.environ.get("FLASK_ENV", "production")
    return CONFIG_MAP.get(env, ProductionConfig)
