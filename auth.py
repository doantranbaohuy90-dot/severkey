# auth.py
# Module xác thực tài khoản/mật khẩu người dùng cho key server
# Cải tiến: session, phân quyền, rate limit, audit log, token API
# Tài khoản mặc định: baohuy / baohuy

import os
import json
import hmac
import hashlib
import secrets
import time
import threading
from datetime import datetime, timezone
from functools import wraps

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
ACCOUNT_FILE = os.path.join(DATA_DIR, "accounts.json")
SESSION_FILE = os.path.join(DATA_DIR, "sessions.json")
AUDIT_FILE = os.path.join(DATA_DIR, "audit.json")
RATELIMIT_FILE = os.path.join(DATA_DIR, "ratelimit.json")
TOKEN_FILE = os.path.join(DATA_DIR, "api_tokens.json")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

lock = threading.Lock()

# ---------------- CAU HINH ----------------

SESSION_TTL = int(os.environ.get("SESSION_TTL", "86400"))       # 24h
SESSION_MAX_PER_USER = int(os.environ.get("SESSION_MAX_PER_USER", "5"))
PBKDF2_ITER = int(os.environ.get("PBKDF2_ITER", "200000"))

# Tai khoan mac dinh
DEFAULT_USER = os.environ.get("DEFAULT_USER", "baohuy")
DEFAULT_USER_PASS = os.environ.get("DEFAULT_USER_PASS", "baohuy")

# Rate limit dang nhap
LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_WINDOW_SEC = int(os.environ.get("LOGIN_WINDOW_SEC", "300"))  # 5 phut
LOGIN_LOCK_SEC = int(os.environ.get("LOGIN_LOCK_SEC", "900"))       # 15 phut

# Mat khau toi thieu
MIN_PASSWORD_LEN = int(os.environ.get("MIN_PASSWORD_LEN", "6"))
MIN_USERNAME_LEN = int(os.environ.get("MIN_USERNAME_LEN", "3"))

# API token TTL (0 = khong het han)
API_TOKEN_TTL = int(os.environ.get("API_TOKEN_TTL", "0"))


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


def now_sec():
    return int(time.time())


def fmt_time(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def gen_id(n=8):
    return secrets.token_hex(n)


# ---------------- HASH MAT KHAU ----------------


def hash_password(password, salt=None):
    # Băm mật khẩu PBKDF2-SHA256 với salt ngẫu nhiên
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
    # So sánh constant-time
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


def check_password_strength(password):
    # Trả về (ok, lý do)
    if not password or len(password) < MIN_PASSWORD_LEN:
        return False, "password_too_short"
    if password.lower() in ("123456", "password", "admin", "baohuy"):
        return False, "password_too_weak"
    return True, None


# ---------------- AUDIT LOG ----------------


def audit(event, data=None, ip=None, actor=None):
    # Ghi audit log cho hành động nhạy cảm
    logs = read_json(AUDIT_FILE, [])
    logs.append({
        "time": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "actor": actor,
        "ip": ip,
        "data": data or {},
    })
    if len(logs) > 10000:
        logs = logs[-10000:]
    write_json(AUDIT_FILE, logs)


def load_audit(n=100):
    logs = read_json(AUDIT_FILE, [])
    return logs[-n:][::-1]


# ---------------- RATE LIMIT ----------------


def _load_ratelimit():
    return read_json(RATELIMIT_FILE, {})


def _save_ratelimit(d):
    write_json(RATELIMIT_FILE, d)


def rate_limit_check(key):
    # key = username hoac ip
    rl = _load_ratelimit()
    now = now_sec()
    rec = rl.get(key, {"attempts": [], "locked_until": 0})
    # Xoa attempts cu ngoai window
    rec["attempts"] = [t for t in rec.get("attempts", []) if now - t < LOGIN_WINDOW_SEC]
    if rec.get("locked_until", 0) > now:
        remaining = rec["locked_until"] - now
        rl[key] = rec
        _save_ratelimit(rl)
        return False, remaining
    rl[key] = rec
    _save_ratelimit(rl)
    return True, 0


def rate_limit_fail(key):
    # Ghi nhan 1 lan that bai
    rl = _load_ratelimit()
    now = now_sec()
    rec = rl.get(key, {"attempts": [], "locked_until": 0})
    rec["attempts"] = [t for t in rec.get("attempts", []) if now - t < LOGIN_WINDOW_SEC]
    rec["attempts"].append(now)
    if len(rec["attempts"]) >= LOGIN_MAX_ATTEMPTS:
        rec["locked_until"] = now + LOGIN_LOCK_SEC
        rec["attempts"] = []
    rl[key] = rec
    _save_ratelimit(rl)
    return rec.get("locked_until", 0)


def rate_limit_reset(key):
    # Xoa khi dang nhap thanh cong
    rl = _load_ratelimit()
    if key in rl:
        del rl[key]
        _save_ratelimit(rl)


def rate_limit_status(key):
    rl = _load_ratelimit()
    rec = rl.get(key)
    if not rec:
        return {"locked": False, "attempts": 0}
    now = now_sec()
    if rec.get("locked_until", 0) > now:
        return {"locked": True, "remaining": rec["locked_until"] - now}
    attempts = [t for t in rec.get("attempts", []) if now - t < LOGIN_WINDOW_SEC]
    return {"locked": False, "attempts": len(attempts)}


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


def find_account_by_telegram(telegram_id):
    accounts = load_accounts()
    tid = str(telegram_id)
    for uid, rec in accounts.items():
        if str(rec.get("telegramId")) == tid:
            return uid, rec
    return None, None


def find_account_by_email(email):
    accounts = load_accounts()
    em = str(email).strip().lower()
    for uid, rec in accounts.items():
        if rec.get("email", "").lower() == em:
            return uid, rec
    return None, None


def ensure_default_user():
    # Tạo baohuy/baohuy nếu chưa tồn tại
    uid, _ = find_account_by_username(DEFAULT_USER)
    if uid:
        return uid
    accounts = load_accounts()
    new_uid = gen_id(8)
    accounts[new_uid] = {
        "username": DEFAULT_USER,
        "password": hash_password(DEFAULT_USER_PASS),
        "createdAt": now_ms(),
        "active": True,
        "telegramId": None,
        "deviceId": None,
        "ip": None,
        "email": None,
        "key": None,
        "role": "admin",
        "lastLogin": None,
        "loginCount": 0,
    }
    save_accounts(accounts)
    audit("default_user_created", {"uid": new_uid, "username": DEFAULT_USER})
    return new_uid


def register_account(username, password, telegram_id=None, device_id=None,
                     ip=None, email=None, role="user"):
    # Đăng ký tài khoản mới
    username = str(username).strip()
    if not username or not password:
        return False, "missing_params"
    if len(username) < MIN_USERNAME_LEN:
        return False, "username_too_short"
    if not username.replace("_", "").replace("-", "").isalnum():
        return False, "username_invalid"
    ok, err = check_password_strength(password)
    if not ok:
        return False, err
    if find_account_by_username(username)[0]:
        return False, "username_exists"
    if email and find_account_by_email(email)[0]:
        return False, "email_exists"

    accounts = load_accounts()
    uid = gen_id(8)
    accounts[uid] = {
        "username": username,
        "password": hash_password(password),
        "createdAt": now_ms(),
        "active": True,
        "telegramId": str(telegram_id) if telegram_id else None,
        "deviceId": device_id,
        "ip": ip,
        "email": email,
        "key": None,
        "role": role,
        "lastLogin": None,
        "loginCount": 0,
    }
    save_accounts(accounts)
    audit("register", {"uid": uid, "username": username}, ip=ip, actor=username)
    return True, uid


def authenticate_account(username, password, ip=None, check_rate=True):
    # Xác thực tài khoản với rate limit
    if check_rate:
        allowed, remaining = rate_limit_check(f"u:{username}")
        if not allowed:
            audit("login_locked", {"username": username, "remaining": remaining},
                  ip=ip, actor=username)
            return None, "locked"
        allowed_ip, remaining_ip = rate_limit_check(f"i:{ip}" if ip else "i:unknown")
        if not allowed_ip:
            audit("login_locked_ip", {"ip": ip, "remaining": remaining_ip},
                  ip=ip, actor=username)
            return None, "locked_ip"

    uid, rec = find_account_by_username(username)
    if not rec:
        if check_rate:
            rate_limit_fail(f"u:{username}")
            rate_limit_fail(f"i:{ip}" if ip else "i:unknown")
        audit("login_fail", {"username": username, "reason": "not_found"},
              ip=ip, actor=username)
        return None, "not_found"
    if not rec.get("active", True):
        audit("login_fail", {"username": username, "reason": "disabled"},
              ip=ip, actor=username)
        return None, "disabled"
    if not verify_password(password, rec["password"]):
        if check_rate:
            rate_limit_fail(f"u:{username}")
            rate_limit_fail(f"i:{ip}" if ip else "i:unknown")
        audit("login_fail", {"username": username, "reason": "wrong_password"},
              ip=ip, actor=username)
        return None, "wrong_password"

    # Thanh cong, reset rate limit
    if check_rate:
        rate_limit_reset(f"u:{username}")
        rate_limit_reset(f"i:{ip}" if ip else "i:unknown")

    accounts = load_accounts()
    accounts[uid]["lastLogin"] = now_ms()
    accounts[uid]["loginCount"] = accounts[uid].get("loginCount", 0) + 1
    accounts[uid]["lastIp"] = ip
    save_accounts(accounts)
    audit("login_ok", {"uid": uid, "username": username}, ip=ip, actor=username)
    return uid, None


def get_account(uid):
    return load_accounts().get(uid)


def set_account_key(uid, key):
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
    audit("bind_telegram", {"uid": uid, "telegramId": str(telegram_id)})
    return True


def toggle_account(uid, actor=None):
    accounts = load_accounts()
    if uid not in accounts:
        return None
    accounts[uid]["active"] = not accounts[uid].get("active", True)
    save_accounts(accounts)
    audit("toggle_account", {"uid": uid, "active": accounts[uid]["active"]}, actor=actor)
    return accounts[uid]["active"]


def change_account_password(uid, old_pw, new_pw, actor=None):
    accounts = load_accounts()
    if uid not in accounts:
        return False, "not_found"
    if not verify_password(old_pw, accounts[uid]["password"]):
        audit("changepw_fail", {"uid": uid}, actor=actor)
        return False, "wrong_password"
    ok, err = check_password_strength(new_pw)
    if not ok:
        return False, err
    accounts[uid]["password"] = hash_password(new_pw)
    accounts[uid]["passwordChangedAt"] = now_ms()
    save_accounts(accounts)
    audit("changepw_ok", {"uid": uid}, actor=actor)
    return True, None


def reset_password_by_admin(uid, new_pw, actor=None):
    # Admin đặt lại mật khẩu không cần mk cũ
    accounts = load_accounts()
    if uid not in accounts:
        return False, "not_found"
    ok, err = check_password_strength(new_pw)
    if not ok:
        return False, err
    accounts[uid]["password"] = hash_password(new_pw)
    accounts[uid]["passwordChangedAt"] = now_ms()
    save_accounts(accounts)
    # Huy toan bo session cua user
    destroy_all_sessions_of(uid)
    audit("admin_resetpw", {"uid": uid}, actor=actor)
    return True, None


def set_account_role(uid, role, actor=None):
    accounts = load_accounts()
    if uid not in accounts:
        return False, "not_found"
    if role not in ("admin", "operator", "viewer", "ctv", "user"):
        return False, "invalid_role"
    accounts[uid]["role"] = role
    save_accounts(accounts)
    audit("set_role", {"uid": uid, "role": role}, actor=actor)
    return True, None


def delete_account(uid, actor=None):
    # Xóa tài khoản và key liên quan
    accounts = load_accounts()
    if uid not in accounts:
        return False
    key = accounts[uid].get("key")
    username = accounts[uid].get("username")
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
    destroy_all_sessions_of(uid)
    audit("delete_account", {"uid": uid, "username": username}, actor=actor)
    return True


def list_accounts():
    # Danh sách tài khoản rút gọn
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
            "lastLogin": rec.get("lastLogin"),
            "lastLoginText": fmt_time(rec.get("lastLogin")) if rec.get("lastLogin") else "-",
            "loginCount": rec.get("loginCount", 0),
            "telegramId": rec.get("telegramId"),
            "email": rec.get("email"),
            "key": rec.get("key"),
        })
    return result


# ---------------- SESSION ----------------


def load_sessions():
    return read_json(SESSION_FILE, {})


def save_sessions(s):
    write_json(SESSION_FILE, s)


def _cleanup_expired(sessions):
    now = now_ms()
    return {t: s for t, s in sessions.items() if s["expiresAt"] > now}


def create_session(uid, ip=None, user_agent=None):
    # Tạo session token mới, giới hạn số session mỗi user
    sessions = _cleanup_expired(load_sessions())

    # Giới hạn session mỗi user
    user_sessions = [(t, s) for t, s in sessions.items() if s["uid"] == uid]
    if len(user_sessions) >= SESSION_MAX_PER_USER:
        # Xoa session cu nhat
        user_sessions.sort(key=lambda x: x[1].get("createdAt", 0))
        for t, _ in user_sessions[:len(user_sessions) - SESSION_MAX_PER_USER + 1]:
            del sessions[t]

    token = secrets.token_urlsafe(32)
    sessions[token] = {
        "uid": uid,
        "createdAt": now_ms(),
        "expiresAt": now_ms() + SESSION_TTL * 1000,
        "ip": ip,
        "userAgent": user_agent,
    }
    save_sessions(sessions)
    return token


def get_session(token):
    if not token:
        return None
    sessions = load_sessions()
    s = sessions.get(token)
    if not s:
        return None
    if now_ms() > s["expiresAt"]:
        del sessions[token]
        save_sessions(sessions)
        return None
    return s


def destroy_session(token):
    sessions = load_sessions()
    if token in sessions:
        del sessions[token]
        save_sessions(sessions)
        return True
    return False


def destroy_all_sessions_of(uid):
    sessions = load_sessions()
    before = len(sessions)
    sessions = {t: s for t, s in sessions.items() if s["uid"] != uid}
    save_sessions(sessions)
    return before - len(sessions)


def cleanup_sessions():
    sessions = load_sessions()
    cleaned = _cleanup_expired(sessions)
    save_sessions(cleaned)
    return len(sessions) - len(cleaned)


def list_sessions_of(uid):
    sessions = load_sessions()
    result = []
    for t, s in sessions.items():
        if s["uid"] == uid:
            result.append({
                "token_preview": t[:8] + "...",
                "createdAt": s.get("createdAt"),
                "createdAtText": fmt_time(s.get("createdAt", 0)),
                "expiresAt": s.get("expiresAt"),
                "expiresAtText": fmt_time(s.get("expiresAt", 0)),
                "ip": s.get("ip"),
                "userAgent": s.get("userAgent"),
            })
    return result


def list_all_sessions():
    sessions = load_sessions()
    result = []
    for t, s in sessions.items():
        result.append({
            "token_preview": t[:8] + "...",
            "uid": s.get("uid"),
            "createdAtText": fmt_time(s.get("createdAt", 0)),
            "expiresAtText": fmt_time(s.get("expiresAt", 0)),
            "ip": s.get("ip"),
        })
    return result


# ---------------- API TOKEN ----------------


def load_tokens():
    return read_json(TOKEN_FILE, {})


def save_tokens(t):
    write_json(TOKEN_FILE, t)


def create_api_token(uid, name=None, expires_in_days=0):
    # Tạo API token lâu dài cho user
    tokens = load_tokens()
    token = "k_" + secrets.token_urlsafe(32)
    expires_at = 0
    if expires_in_days > 0:
        expires_at = now_ms() + expires_in_days * 24 * 60 * 60 * 1000
    tokens[token] = {
        "uid": uid,
        "name": name or "default",
        "createdAt": now_ms(),
        "expiresAt": expires_at,
        "active": True,
        "lastUsed": None,
    }
    save_tokens(tokens)
    audit("api_token_create", {"uid": uid, "name": name})
    return token


def get_api_token(token):
    if not token:
        return None
    tokens = load_tokens()
    rec = tokens.get(token)
    if not rec or not rec.get("active", True):
        return None
    if rec.get("expiresAt", 0) and now_ms() > rec["expiresAt"]:
        return None
    # Cap nhat last used
    tokens[token]["lastUsed"] = now_ms()
    save_tokens(tokens)
    return rec


def revoke_api_token(token):
    tokens = load_tokens()
    if token in tokens:
        tokens[token]["active"] = False
        save_tokens(tokens)
        audit("api_token_revoke", {"token_preview": token[:8]})
        return True
    return False


def list_api_tokens_of(uid):
    tokens = load_tokens()
    result = []
    for t, rec in tokens.items():
        if rec.get("uid") == uid:
            result.append({
                "token_preview": t[:10] + "...",
                "name": rec.get("name"),
                "active": rec.get("active", True),
                "createdAtText": fmt_time(rec.get("createdAt", 0)),
                "expiresAtText": fmt_time(rec["expiresAt"]) if rec.get("expiresAt") else "không hết hạn",
                "lastUsedText": fmt_time(rec["lastUsed"]) if rec.get("lastUsed") else "-",
            })
    return result


# ---------------- PHAN QUYEN ----------------


ROLE_PERMS = {
    "admin":    {"read", "write", "admin", "ctv", "block", "delete", "issue", "read_self", "issue_self"},
    "operator": {"read", "write", "ctv", "issue", "read_self", "issue_self"},
    "ctv":      {"read", "issue", "read_self", "issue_self"},
    "viewer":   {"read", "read_self"},
    "user":     {"read_self", "issue_self"},
}

ROLE_LEVEL = {
    "admin": 100,
    "operator": 50,
    "ctv": 30,
    "viewer": 10,
    "user": 1,
}


def has_permission(role, perm):
    return perm in ROLE_PERMS.get(role, set())


def role_level(role):
    return ROLE_LEVEL.get(role, 0)


def can_manage(actor_role, target_role):
    # Actor co the quan ly target neu level cao hon
    return role_level(actor_role) > role_level(target_role)
