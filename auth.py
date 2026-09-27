# auth.py
# Module xác thực tài khoản/mật khẩu người dùng cho key server
# Tài khoản mặc định: baohuy / baohuy
# Hash mật khẩu PBKDF2-SHA256, session token ngẫu nhiên

import os
import json
import hmac
import hashlib
import secrets
import time
import threading
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
ACCOUNT_FILE = os.path.join(DATA_DIR, "accounts.json")
SESSION_FILE = os.path.join(DATA_DIR, "sessions.json")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

lock = threading.Lock()

SESSION_TTL = int(os.environ.get("SESSION_TTL", "86400"))  # 24h
PBKDF2_ITER = 200_000

# Tài khoản người dùng mặc định
DEFAULT_USER = os.environ.get("DEFAULT_USER", "baohuy")
DEFAULT_USER_PASS = os.environ.get("DEFAULT_USER_PASS", "baohuy")


# ---------------- IO ----------------


def read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    with lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def now_ms():
    return int(time.time() * 1000)


def fmt_time(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# ---------------- HASH MAT KHAU ----------------


def hash_password(password, salt=None):
    # Băm mật khẩu bằng PBKDF2-SHA256 với salt ngẫu nhiên
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITER,
    )
    return f"pbkdf2_sha256${PBKDF2_ITER}${salt}${dk.hex()}"


def verify_password(password, stored):
    # Kiểm tra mật khẩu với hash đã lưu
    try:
        algo, iter_s, salt, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iter_s),
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# ---------------- TAI KHOAN ----------------


def load_accounts():
    return read_json(ACCOUNT_FILE, {})


def save_accounts(a):
    write_json(ACCOUNT_FILE, a)


def find_account_by_username(username):
    # Tìm tài khoản không phân biệt hoa thường
    accounts = load_accounts()
    uname = str(username).strip().lower()
    for uid, rec in accounts.items():
        if rec.get("username", "").lower() == uname:
            return uid, rec
    return None, None


def ensure_default_user():
    # Tạo tài khoản baohuy/baohuy nếu chưa tồn tại
    uid, _ = find_account_by_username(DEFAULT_USER)
    if uid:
        return uid
    accounts = load_accounts()
    new_uid = secrets.token_hex(8)
    accounts[new_uid] = {
        "username": DEFAULT_USER,
        "password": hash_password(DEFAULT_USER_PASS),
        "createdAt": now_ms(),
        "active": True,
        "telegramId": None,
        "deviceId": None,
        "ip": None,
        "key": None,
        "role": "user",
    }
    save_accounts(accounts)
    return new_uid


def register_account(username, password, telegram_id=None, device_id=None, ip=None):
    # Đăng ký tài khoản mới
    username = str(username).strip()
    if not username or not password:
        return False, "missing_params"
    if len(password) < 6:
        return False, "password_too_short"
    if len(username) < 3:
        return False, "username_too_short"
    if find_account_by_username(username)[0]:
        return False, "username_exists"
    accounts = load_accounts()
    uid = secrets.token_hex(8)
    accounts[uid] = {
        "username": username,
        "password": hash_password(password),
        "createdAt": now_ms(),
        "active": True,
        "telegramId": str(telegram_id) if telegram_id else None,
        "deviceId": device_id,
        "ip": ip,
        "key": None,
        "role": "user",
    }
    save_accounts(accounts)
    return True, uid


def authenticate_account(username, password):
    # Xác thực tài khoản, trả về (uid, error)
    uid, rec = find_account_by_username(username)
    if not rec:
        return None, "not_found"
    if not rec.get("active", True):
        return None, "disabled"
    if not verify_password(password, rec["password"]):
        return None, "wrong_password"
    return uid, None


def get_account(uid):
    return load_accounts().get(uid)


def set_account_key(uid, key):
    # Gán key vào tài khoản
    accounts = load_accounts()
    if uid not in accounts:
        return False
    accounts[uid]["key"] = key
    accounts[uid]["keyIssuedAt"] = now_ms()
    save_accounts(accounts)
    return True


def get_account_key(uid):
    return load_accounts().get(uid, {}).get("key")


def bind_account_telegram(uid, telegram_id):
    accounts = load_accounts()
    if uid not in accounts:
        return False
    accounts[uid]["telegramId"] = str(telegram_id)
    save_accounts(accounts)
    return True


def find_account_by_telegram(telegram_id):
    accounts = load_accounts()
    tid = str(telegram_id)
    for uid, rec in accounts.items():
        if str(rec.get("telegramId")) == tid:
            return uid, rec
    return None, None


def toggle_account(uid):
    # Bật/tắt tài khoản
    accounts = load_accounts()
    if uid not in accounts:
        return None
    accounts[uid]["active"] = not accounts[uid].get("active", True)
    save_accounts(accounts)
    return accounts[uid]["active"]


def change_account_password(uid, old_pw, new_pw):
    # Đổi mật khẩu tài khoản
    accounts = load_accounts()
    if uid not in accounts:
        return False, "not_found"
    if not verify_password(old_pw, accounts[uid]["password"]):
        return False, "wrong_password"
    if len(new_pw) < 6:
        return False, "too_short"
    accounts[uid]["password"] = hash_password(new_pw)
    save_accounts(accounts)
    return True, None


def set_account_role(uid, role):
    accounts = load_accounts()
    if uid not in accounts:
        return False, "not_found"
    if role not in ("admin", "operator", "viewer", "ctv", "user"):
        return False, "invalid_role"
    accounts[uid]["role"] = role
    save_accounts(accounts)
    return True, None


def delete_account(uid):
    # Xóa tài khoản và key liên quan
    accounts = load_accounts()
    if uid not in accounts:
        return False
    key = accounts[uid].get("key")
    del accounts[uid]
    save_accounts(accounts)
    if key:
        key_file = os.path.join(DATA_DIR, "keys.json")
        device_file = os.path.join(DATA_DIR, "devices.json")
        keys = read_json(key_file, {})
        if key in keys:
            del keys[key]
            write_json(key_file, keys)
        devices = read_json(device_file, {})
        if key in devices:
            del devices[key]
            write_json(device_file, devices)
    return True


def list_accounts():
    # Trả về danh sách tài khoản rút gọn (không kèm hash mật khẩu)
    accounts = load_accounts()
    result = []
    for uid, rec in accounts.items():
        result.append({
            "uid": uid,
            "username": rec.get("username"),
            "role": rec.get("role", "user"),
            "active": rec.get("active", True),
            "createdAt": rec.get("createdAt"),
            "createdAtText": fmt_time(rec.get("createdAt", now_ms())),
            "telegramId": rec.get("telegramId"),
            "key": rec.get("key"),
        })
    return result


# ---------------- SESSION ----------------


def create_session(uid):
    # Tạo session token mới và dọn session hết hạn
    sessions = read_json(SESSION_FILE, {})
    token = secrets.token_urlsafe(32)
    sessions[token] = {
        "uid": uid,
        "createdAt": now_ms(),
        "expiresAt": now_ms() + SESSION_TTL * 1000,
    }
    now = now_ms()
    sessions = {t: s for t, s in sessions.items() if s["expiresAt"] > now}
    write_json(SESSION_FILE, sessions)
    return token


def get_session(token):
    # Lấy session nếu còn hiệu lực
    if not token:
        return None
    sessions = read_json(SESSION_FILE, {})
    s = sessions.get(token)
    if not s:
        return None
    if now_ms() > s["expiresAt"]:
        del sessions[token]
        write_json(SESSION_FILE, sessions)
        return None
    return s


def destroy_session(token):
    sessions = read_json(SESSION_FILE, {})
    if token in sessions:
        del sessions[token]
        write_json(SESSION_FILE, sessions)
        return True
    return False


def destroy_all_sessions_of(uid):
    # Hủy toàn bộ session của một tài khoản
    sessions = read_json(SESSION_FILE, {})
    before = len(sessions)
    sessions = {t: s for t, s in sessions.items() if s["uid"] != uid}
    write_json(SESSION_FILE, sessions)
    return before - len(sessions)


def cleanup_sessions():
    # Dọn session hết hạn, trả về số lượng đã xóa
    sessions = read_json(SESSION_FILE, {})
    now = now_ms()
    cleaned = {t: s for t, s in sessions.items() if s["expiresAt"] > now}
    write_json(SESSION_FILE, cleaned)
    return len(sessions) - len(cleaned)


def list_sessions():
    return read_json(SESSION_FILE, {})


# ---------------- PHAN QUYEN ----------------


ROLE_PERMS = {
    "admin": {"read", "write", "admin", "ctv", "block", "delete", "issue"},
    "operator": {"read", "write", "ctv", "issue"},
    "ctv": {"read", "issue"},
    "viewer": {"read"},
    "user": {"read_self", "issue_self"},
}


def has_permission(role, perm):
    return perm in ROLE_PERMS.get(role, set())
