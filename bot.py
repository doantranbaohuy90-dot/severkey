# bot.py
# Máy chủ key đầy đủ: API, Web Dashboard, Auth, Dylib check, Block thiết bị
# Tính năng mới: hệ thống CTV (cộng tác viên), thêm/xóa ID CTV

import os
import json
import hmac
import hashlib
import secrets
import time
import threading
import base64
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, request, jsonify, render_template_string, make_response, redirect, url_for
import requests

app = Flask(__name__)

# ---------------- CAU HINH ----------------

BOT_TOKEN = os.environ.get("BOT_TOKEN", "6190734534:AAFE2Y1VlLBUv_W3EMwwQ3TkKmMSJWzrHJc")
ADMIN_ID = str(os.environ.get("ADMIN_ID", "5736655322"))
SECRET = os.environ.get("KEY_SECRET", "doi_thanh_bien_moi_truong")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "admin_token_mac_dinh")
WEB_USER = os.environ.get("WEB_USER", "admin")
WEB_PASS = os.environ.get("WEB_PASS", "admin123")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
KEY_FILE = os.path.join(DATA_DIR, "keys.json")
DEVICE_FILE = os.path.join(DATA_DIR, "devices.json")
LOG_FILE = os.path.join(DATA_DIR, "logs.json")
BLOCK_FILE = os.path.join(DATA_DIR, "blocked.json")
USER_FILE = os.path.join(DATA_DIR, "users.json")
CTV_FILE = os.path.join(DATA_DIR, "ctv.json")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

lock = threading.Lock()
DEFAULT_MAX_DEVICES = int(os.environ.get("DEFAULT_MAX_DEVICES", "1"))
DEFAULT_DAYS = int(os.environ.get("DEFAULT_DAYS", "1"))

AUTO_ISSUE_ENABLED = os.environ.get("AUTO_ISSUE_ENABLED", "true").lower() == "true"
AUTO_ISSUE_ONCE = os.environ.get("AUTO_ISSUE_ONCE", "true").lower() == "true"

# Quyen CTV: so ngay toi da duoc cap, so key toi da duoc tao
CTV_MAX_DAYS = int(os.environ.get("CTV_MAX_DAYS", "30"))
CTV_MAX_KEYS = int(os.environ.get("CTV_MAX_KEYS", "50"))

ALLOWED_DYLIB_HASHES = set(
    h.strip().lower() for h in os.environ.get("ALLOWED_DYLIB_HASHES", "").split(",") if h.strip()
)
BLOCKED_DYLIB_SIGNATURES = set(
    s.strip().lower() for s in os.environ.get("BLOCKED_DYLIB_SIGNATURES", "").split(",") if s.strip()
)


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


def load_keys():
    return read_json(KEY_FILE, {})


def save_keys(k):
    write_json(KEY_FILE, k)


def load_devices():
    return read_json(DEVICE_FILE, {})


def save_devices(d):
    write_json(DEVICE_FILE, d)


def load_blocked():
    return read_json(BLOCK_FILE, {"keys": {}, "devices": {}})


def save_blocked(b):
    write_json(BLOCK_FILE, b)


def load_users():
    return read_json(USER_FILE, {})


def save_users(u):
    write_json(USER_FILE, u)


def load_ctv():
    return read_json(CTV_FILE, {})


def save_ctv(c):
    write_json(CTV_FILE, c)


def append_log(event, data):
    logs = read_json(LOG_FILE, [])
    logs.append({
        "time": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "data": data,
    })
    if len(logs) > 5000:
        logs = logs[-5000:]
    write_json(LOG_FILE, logs)


# ---------------- TIEN ICH ----------------


def generate_key():
    raw = secrets.token_hex(12).upper()
    return "-".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def sign_key(key, expires_at):
    payload = f"{key}|{expires_at}".encode("utf-8")
    return hmac.new(SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def now_ms():
    return int(time.time() * 1000)


def fmt_time(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def get_client_ip(req):
    fwd = req.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return req.remote_addr or "unknown"


def send_message(chat_id, text):
    try:
        requests.post(
            f"{API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print("Lỗi gửi tin nhắn:", e)


# ---------------- CTV ----------------


def is_ctv(user_id):
    ctv = load_ctv()
    return str(user_id) in ctv


def is_admin(user_id):
    return str(user_id) == ADMIN_ID


def has_perm(user_id):
    return is_admin(user_id) or is_ctv(user_id)


def add_ctv(user_id, name=None, max_keys=None, max_days=None):
    ctv = load_ctv()
    ctv[str(user_id)] = {
        "name": name or f"ctv_{user_id}",
        "maxKeys": int(max_keys) if max_keys is not None else CTV_MAX_KEYS,
        "maxDays": int(max_days) if max_days is not None else CTV_MAX_DAYS,
        "keysCreated": ctv.get(str(user_id), {}).get("keysCreated", 0),
        "addedAt": now_ms(),
        "active": True,
    }
    save_ctv(ctv)
    append_log("ctv_add", {"user_id": str(user_id), "name": name})
    return True


def remove_ctv(user_id):
    ctv = load_ctv()
    if str(user_id) in ctv:
        del ctv[str(user_id)]
        save_ctv(ctv)
        append_log("ctv_remove", {"user_id": str(user_id)})
        return True
    return False


def toggle_ctv(user_id):
    ctv = load_ctv()
    uid = str(user_id)
    if uid not in ctv:
        return None
    ctv[uid]["active"] = not ctv[uid].get("active", True)
    save_ctv(ctv)
    append_log("ctv_toggle", {"user_id": uid, "active": ctv[uid]["active"]})
    return ctv[uid]["active"]


def increment_ctv_count(user_id):
    ctv = load_ctv()
    uid = str(user_id)
    if uid in ctv:
        ctv[uid]["keysCreated"] = ctv[uid].get("keysCreated", 0) + 1
        save_ctv(ctv)


def ctv_can_create(user_id, days=1):
    ctv = load_ctv()
    uid = str(user_id)
    if uid not in ctv:
        return False, "not_ctv"
    rec = ctv[uid]
    if not rec.get("active", True):
        return False, "ctv_disabled"
    if days > rec.get("maxDays", CTV_MAX_DAYS):
        return False, "exceed_max_days"
    if rec.get("keysCreated", 0) >= rec.get("maxKeys", CTV_MAX_KEYS):
        return False, "exceed_max_keys"
    return True, None


# ---------------- DYLIB ----------------


def check_dylib_list(dylibs):
    blocked, unknown, allowed = [], [], []

    for d in dylibs:
        name = str(d.get("name", "")).lower()
        h = str(d.get("hash", "")).lower()

        is_blocked = any(sig and (sig in name or sig in h) for sig in BLOCKED_DYLIB_SIGNATURES)
        if is_blocked:
            blocked.append({"name": name, "hash": h, "reason": "signature_blocked"})
            continue

        if ALLOWED_DYLIB_HASHES:
            if h in ALLOWED_DYLIB_HASHES:
                allowed.append({"name": name, "hash": h})
            else:
                unknown.append({"name": name, "hash": h})
        else:
            allowed.append({"name": name, "hash": h})

    injected = len(blocked) > 0
    return {
        "ok": not injected and len(unknown) == 0,
        "blocked": blocked,
        "unknown": unknown,
        "allowed": allowed,
        "injected": injected,
    }


# ---------------- BLOCK ----------------


def block_device(key, device_id, reason):
    b = load_blocked()
    b.setdefault("devices", {})[device_id] = {"key": key, "reason": reason, "time": now_ms()}
    save_blocked(b)
    append_log("device_block", {"key": key, "device": device_id, "reason": reason})


def unblock_device(device_id):
    b = load_blocked()
    if device_id in b.get("devices", {}):
        del b["devices"][device_id]
        save_blocked(b)
        append_log("device_unblock", {"device": device_id})
        return True
    return False


def block_key(key, reason):
    b = load_blocked()
    b.setdefault("keys", {})[key] = {"reason": reason, "time": now_ms()}
    save_blocked(b)
    append_log("key_block", {"key": key, "reason": reason})


def unblock_key(key):
    b = load_blocked()
    if key in b.get("keys", {}):
        del b["keys"][key]
        save_blocked(b)
        append_log("key_unblock", {"key": key})
        return True
    return False


def is_device_blocked(device_id):
    return device_id in load_blocked().get("devices", {})


def is_key_blocked(key):
    return key in load_blocked().get("keys", {})


# ---------------- NGHIEP VU KEY ----------------


def create_key(days, owner, max_devices=DEFAULT_MAX_DEVICES, user_id=None, created_by=None):
    key = generate_key()
    expires_at = now_ms() + days * 24 * 60 * 60 * 1000
    signature = sign_key(key, expires_at)
    keys = load_keys()
    keys[key] = {
        "owner": owner,
        "expiresAt": expires_at,
        "signature": signature,
        "active": True,
        "maxDevices": int(max_devices),
        "createdAt": now_ms(),
        "userId": user_id,
        "createdBy": str(created_by) if created_by else None,
    }
    save_keys(keys)

    if user_id:
        users = load_users()
        users[str(user_id)] = {
            "key": key,
            "owner": owner,
            "createdAt": now_ms(),
        }
        save_users(users)

    if created_by:
        increment_ctv_count(created_by)

    append_log("key_create", {
        "key": key, "owner": owner, "days": days, "maxDevices": max_devices,
        "userId": user_id, "createdBy": str(created_by) if created_by else None,
    })
    return key, expires_at, signature


def get_key_by_user(user_id):
    users = load_users()
    rec = users.get(str(user_id))
    if not rec:
        return None
    return rec.get("key")


def get_or_create_key_for_user(user_id, owner=None, days=None, max_devices=None, created_by=None):
    if AUTO_ISSUE_ONCE:
        existing = get_key_by_user(user_id)
        if existing:
            keys = load_keys()
            if existing in keys and keys[existing].get("active") and now_ms() < keys[existing]["expiresAt"]:
                return {"created": False, "key": existing, "record": keys[existing]}

    days = days if days is not None else DEFAULT_DAYS
    owner = owner or f"user_{user_id}"
    max_devices = max_devices if max_devices is not None else DEFAULT_MAX_DEVICES
    key, exp, sig = create_key(days, owner, max_devices, user_id=user_id, created_by=created_by)
    return {"created": True, "key": key, "expiresAt": exp, "signature": sig, "record": load_keys()[key]}


def add_days(key, days):
    keys = load_keys()
    if key not in keys:
        return None
    base = max(keys[key]["expiresAt"], now_ms())
    new_exp = base + days * 24 * 60 * 60 * 1000
    keys[key]["expiresAt"] = new_exp
    keys[key]["signature"] = sign_key(key, new_exp)
    keys[key]["active"] = True
    save_keys(keys)
    append_log("key_adddays", {"key": key, "days": days, "newExpiresAt": new_exp})
    return new_exp


def set_expiry(key, days_from_now):
    keys = load_keys()
    if key not in keys:
        return None
    new_exp = now_ms() + days_from_now * 24 * 60 * 60 * 1000
    keys[key]["expiresAt"] = new_exp
    keys[key]["signature"] = sign_key(key, new_exp)
    keys[key]["active"] = True
    save_keys(keys)
    append_log("key_setexp", {"key": key, "daysFromNow": days_from_now, "newExpiresAt": new_exp})
    return new_exp


def get_days_left(key):
    r = load_keys().get(key)
    if not r:
        return None
    ms = r["expiresAt"] - now_ms()
    return max(0, ms // (24 * 60 * 60 * 1000))


def revoke_key(key):
    keys = load_keys()
    if key not in keys:
        return False
    keys[key]["active"] = False
    save_keys(keys)
    append_log("key_revoke", {"key": key})
    return True


def reset_devices(key):
    devices = load_devices()
    if key in devices:
        del devices[key]
        save_devices(devices)
    append_log("device_reset", {"key": key})
    return True


def delete_key(key):
    keys = load_keys()
    if key not in keys:
        return False
    user_id = keys[key].get("userId")
    del keys[key]
    save_keys(keys)
    devices = load_devices()
    if key in devices:
        del devices[key]
        save_devices(devices)
    if user_id:
        users = load_users()
        if users.get(str(user_id), {}).get("key") == key:
            del users[str(user_id)]
            save_users(users)
    append_log("key_delete", {"key": key})
    return True


def verify_key(key, device_id, ip, user_agent, dylibs=None):
    if is_key_blocked(key):
        append_log("verify_fail", {"key": key, "reason": "key_blocked", "device": device_id, "ip": ip})
        return {"ok": False, "error": "key_blocked"}
    if is_device_blocked(device_id):
        append_log("verify_fail", {"key": key, "reason": "device_blocked", "device": device_id, "ip": ip})
        return {"ok": False, "error": "device_blocked"}

    keys = load_keys()
    record = keys.get(key)
    if not record:
        append_log("verify_fail", {"key": key, "reason": "not_found", "device": device_id, "ip": ip})
        return {"ok": False, "error": "key_not_found"}
    if not record.get("active"):
        append_log("verify_fail", {"key": key, "reason": "disabled", "device": device_id, "ip": ip})
        return {"ok": False, "error": "key_disabled"}
    if now_ms() > record["expiresAt"]:
        append_log("verify_fail", {"key": key, "reason": "expired", "device": device_id, "ip": ip})
        return {"ok": False, "error": "key_expired"}

    dylib_result = None
    if dylibs is not None:
        dylib_result = check_dylib_list(dylibs)
        if dylib_result["injected"]:
            block_device(key, device_id, "dylib_injected")
            append_log("dylib_injected", {"key": key, "device": device_id, "blocked": dylib_result["blocked"]})
            return {"ok": False, "error": "dylib_injected", "detail": dylib_result, "device_blocked": True}
        if dylib_result["unknown"]:
            append_log("dylib_unknown", {"key": key, "device": device_id, "unknown": dylib_result["unknown"]})
            return {"ok": False, "error": "dylib_unknown", "detail": dylib_result}

    devices = load_devices()
    key_devices = devices.get(key, {})
    max_dev = record.get("maxDevices", DEFAULT_MAX_DEVICES)

    if device_id not in key_devices:
        if len(key_devices) >= max_dev:
            append_log("verify_fail", {"key": key, "reason": "device_limit", "device": device_id, "ip": ip})
            return {"ok": False, "error": "device_limit_reached", "maxDevices": max_dev}
        key_devices[device_id] = {
            "firstSeen": now_ms(),
            "lastSeen": now_ms(),
            "ip": ip,
            "userAgent": user_agent,
            "count": 1,
            "dylibHash": [d.get("hash") for d in (dylibs or [])],
        }
    else:
        key_devices[device_id]["lastSeen"] = now_ms()
        key_devices[device_id]["ip"] = ip
        key_devices[device_id]["userAgent"] = user_agent
        key_devices[device_id]["count"] = key_devices[device_id].get("count", 0) + 1
        key_devices[device_id]["dylibHash"] = [d.get("hash") for d in (dylibs or [])]

    devices[key] = key_devices
    save_devices(devices)
    append_log("verify_ok", {"key": key, "device": device_id, "ip": ip})

    remaining_days = (record["expiresAt"] - now_ms()) // (24 * 60 * 60 * 1000)
    return {
        "ok": True,
        "owner": record["owner"],
        "expiresAt": record["expiresAt"],
        "expiresAtText": fmt_time(record["expiresAt"]),
        "remainingDays": remaining_days,
        "signature": record["signature"],
        "devicesUsed": len(key_devices),
        "maxDevices": max_dev,
        "dylib": dylib_result,
    }


# ---------------- AUTH WEB ----------------


def check_auth(req):
    auth = req.authorization
    if not auth:
        return False
    return auth.username == WEB_USER and auth.password == WEB_PASS


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not check_auth(request):
            return make_response(
                "Yêu cầu xác thực.", 401,
                {"WWW-Authenticate": 'Basic realm="Key Server"'},
            )
        return f(*args, **kwargs)
    return wrapper


def require_admin_token(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.headers.get("X-Admin-Token") != ADMIN_TOKEN:
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


# ---------------- WEB DASHBOARD ----------------


DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Key Server Dashboard</title>
<style>
  body { background:#0d1117; color:#c9d1d9; font-family:monospace; margin:0; padding:16px; }
  h1, h2, h3 { color:#58a6ff; }
  .box { border:1px solid #30363d; padding:12px; margin:12px 0; border-radius:6px; background:#161b22; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th, td { border:1px solid #30363d; padding:6px; text-align:left; }
  th { background:#21262d; color:#58a6ff; }
  input, button, select { background:#0d1117; color:#c9d1d9; border:1px solid #30363d; padding:6px; font-family:monospace; }
  button { background:#238636; cursor:pointer; }
  button:hover { background:#2ea043; }
  .on { color:#3fb950; }
  .off { color:#f85149; }
  .blk { color:#d29922; }
  .user { color:#a371f7; }
  .ctv { color:#f0883e; }
  a { color:#58a6ff; }
</style>
</head>
<body>
<h1>KEY SERVER DASHBOARD</h1>
<div class="box">
  <div>Thời gian: {{ now }}</div>
  <div>Tổng key: {{ total_keys }} | Người dùng: {{ total_users }} | CTV: {{ total_ctv }} | Thiết bị: {{ total_devices }} | Block: {{ total_blocked }}</div>
  <div>Auto issue: {{ 'BẬT' if auto_issue else 'TẮT' }} | Một lần: {{ 'CÓ' if auto_once else 'KHÔNG' }}</div>
</div>

<div class="box">
  <h2>Quản lý CTV</h2>
  <form method="POST" action="/web/addctv">
    <input name="user_id" placeholder="user_id CTV" size="16">
    <input name="name" placeholder="tên CTV" size="16">
    <input name="max_keys" value="{{ ctv_max_keys }}" size="4" title="số key tối đa">
    <input name="max_days" value="{{ ctv_max_days }}" size="4" title="số ngày tối đa">
    <button type="submit">Thêm CTV</button>
  </form>
  <form method="POST" action="/web/removectv">
    <input name="user_id" placeholder="user_id CTV" size="16">
    <button type="submit">Xóa CTV</button>
  </form>
  <table>
    <tr><th>UserID</th><th>Tên</th><th>Trạng thái</th><th>Đã tạo</th><th>Max keys</th><th>Max days</th><th>Thêm lúc</th><th>Hành động</th></tr>
    {% for uid, rec in ctv.items() %}
    <tr>
      <td class="ctv">{{ uid }}</td>
      <td>{{ rec.name }}</td>
      <td class="{{ 'on' if rec.active else 'off' }}">{{ 'ON' if rec.active else 'OFF' }}</td>
      <td>{{ rec.keysCreated or 0 }}</td>
      <td>{{ rec.maxKeys }}</td>
      <td>{{ rec.maxDays }}</td>
      <td>{{ fmt(rec.addedAt) }}</td>
      <td>
        <form method="POST" action="/web/toggle_ctv" style="display:inline">
          <input type="hidden" name="user_id" value="{{ uid }}">
          <button type="submit">{{ 'Tắt' if rec.active else 'Bật' }}</button>
        </form>
      </td>
    </tr>
    {% endfor %}
  </table>
</div>

<div class="box">
  <h2>Phát key thủ công</h2>
  <form method="POST" action="/web/create">
    <input name="days" value="30" placeholder="số ngày" size="6">
    <input name="owner" placeholder="chủ sở hữu" size="16">
    <input name="max_devices" value="1" size="4">
    <button type="submit">Tạo</button>
  </form>
</div>

<div class="box">
  <h2>Phát key tự động theo user</h2>
  <form method="POST" action="/web/issue">
    <input name="user_id" placeholder="user_id" size="16">
    <input name="days" value="{{ default_days }}" size="6">
    <input name="owner" placeholder="chủ sở hữu (tùy chọn)" size="16">
    <input name="max_devices" value="{{ default_max_devices }}" size="4">
    <button type="submit">Cấp key</button>
  </form>
  <form method="POST" action="/web/toggle_auto">
    <button type="submit">{{ 'Tắt' if auto_issue else 'Bật' }} auto issue</button>
  </form>
  <form method="POST" action="/web/toggle_once">
    <button type="submit">{{ 'Tắt' if auto_once else 'Bật' }} một lần / user</button>
  </form>
</div>

<div class="box">
  <h2>Tra cứu user</h2>
  <form method="POST" action="/web/lookup">
    <input name="user_id" placeholder="user_id" size="16">
    <button type="submit">Tra cứu</button>
  </form>
  {% if lookup %}
  <div>User: {{ lookup.user_id }}</div>
  <div>Key: {{ lookup.key }}</div>
  <div>Chủ: {{ lookup.owner }}</div>
  <div>Hết hạn: {{ lookup.expiresAt }}</div>
  <div>Còn: {{ lookup.daysLeft }} ngày</div>
  <div>Thiết bị: {{ lookup.devicesUsed }}/{{ lookup.maxDevices }}</div>
  {% endif %}
</div>

<div class="box">
  <h2>Thao tác key</h2>
  <form method="POST" action="/web/adddays">
    <input name="key" placeholder="key" size="24">
    <input name="days" placeholder="số ngày" size="6">
    <button type="submit">Cộng ngày</button>
  </form>
  <br>
  <form method="POST" action="/web/revoke">
    <input name="key" placeholder="key" size="24">
    <button type="submit">Thu hồi</button>
  </form>
  <br>
  <form method="POST" action="/web/resetdev">
    <input name="key" placeholder="key" size="24">
    <button type="submit">Reset thiết bị</button>
  </form>
  <br>
  <form method="POST" action="/web/delete">
    <input name="key" placeholder="key" size="24">
    <button type="submit">Xóa key</button>
  </form>
</div>

<div class="box">
  <h2>Block thiết bị</h2>
  <form method="POST" action="/web/blockdev">
    <input name="device_id" placeholder="device_id" size="24">
    <input name="reason" placeholder="lý do" size="16">
    <button type="submit">Block</button>
  </form>
  <br>
  <form method="POST" action="/web/unblockdev">
    <input name="device_id" placeholder="device_id" size="24">
    <button type="submit">Bỏ block</button>
  </form>
</div>

<div class="box">
  <h2>Danh sách key</h2>
  <table>
    <tr><th>Key</th><th>Chủ</th><th>UserID</th><th>Tạo bởi</th><th>Trạng thái</th><th>Block</th><th>TB</th><th>Còn</th><th>Hết hạn</th></tr>
    {% for k, v in keys.items() %}
    <tr>
      <td>{{ k }}</td>
      <td>{{ v.owner }}</td>
      <td class="user">{{ v.userId or '-' }}</td>
      <td class="ctv">{{ v.createdBy or '-' }}</td>
      <td class="{{ 'on' if v.active else 'off' }}">{{ 'ON' if v.active else 'OFF' }}</td>
      <td class="{{ 'blk' if blocked_keys.get(k) else '' }}">{{ 'B' if blocked_keys.get(k) else '-' }}</td>
      <td>{{ device_count.get(k, 0) }}/{{ v.maxDevices }}</td>
      <td>{{ days_left.get(k, 0) }}d</td>
      <td>{{ fmt(v.expiresAt) }}</td>
    </tr>
    {% endfor %}
  </table>
</div>

<div class="box">
  <h2>Người dùng đã cấp key</h2>
  <table>
    <tr><th>UserID</th><th>Key</th><th>Chủ</th><th>Thời gian</th></tr>
    {% for uid, rec in users.items() %}
    <tr>
      <td class="user">{{ uid }}</td>
      <td>{{ rec.key }}</td>
      <td>{{ rec.owner }}</td>
      <td>{{ fmt(rec.createdAt) }}</td>
    </tr>
    {% endfor %}
  </table>
</div>

<div class="box">
  <h2>Block list</h2>
  <h3>Key</h3>
  <table>
    <tr><th>Key</th><th>Lý do</th><th>Thời gian</th></tr>
    {% for k, v in blocked.get('keys', {}).items() %}
    <tr><td>{{ k }}</td><td>{{ v.reason }}</td><td>{{ fmt(v.time) }}</td></tr>
    {% endfor %}
  </table>
  <h3>Thiết bị</h3>
  <table>
    <tr><th>Device</th><th>Key</th><th>Lý do</th><th>Thời gian</th></tr>
    {% for d, v in blocked.get('devices', {}).items() %}
    <tr><td>{{ d }}</td><td>{{ v.key }}</td><td>{{ v.reason }}</td><td>{{ fmt(v.time) }}</td></tr>
    {% endfor %}
  </table>
</div>

<div class="box">
  <h2>Log gần đây</h2>
  <table>
    <tr><th>Thời gian</th><th>Sự kiện</th><th>Dữ liệu</th></tr>
    {% for l in logs %}
    <tr><td>{{ l.time }}</td><td>{{ l.event }}</td><td>{{ l.data }}</td></tr>
    {% endfor %}
  </table>
</div>

</body>
</html>
"""


@app.route("/", methods=["GET"])
def web_index():
    if not check_auth(request):
        return make_response(
            "Yêu cầu xác thực.", 401,
            {"WWW-Authenticate": 'Basic realm="Key Server"'},
        )
    keys = load_keys()
    devices = load_devices()
    blocked = load_blocked()
    users = load_users()
    ctv = load_ctv()
    logs = read_json(LOG_FILE, [])[-30:]
    logs.reverse()

    device_count = {k: len(v) for k, v in devices.items()}
    days_left = {k: get_days_left(k) for k in keys}
    blocked_keys = blocked.get("keys", {})

    total_devices = sum(device_count.values())
    total_blocked = len(blocked.get("keys", {})) + len(blocked.get("devices", {}))

    return render_template_string(
        DASHBOARD_HTML,
        now=fmt_time(now_ms()),
        keys=keys,
        users=users,
        ctv=ctv,
        device_count=device_count,
        days_left=days_left,
        blocked_keys=blocked_keys,
        blocked=blocked,
        logs=logs,
        total_keys=len(keys),
        total_users=len(users),
        total_ctv=len(ctv),
        total_devices=total_devices,
        total_blocked=total_blocked,
        auto_issue=AUTO_ISSUE_ENABLED,
        auto_once=AUTO_ISSUE_ONCE,
        default_days=DEFAULT_DAYS,
        default_max_devices=DEFAULT_MAX_DEVICES,
        ctv_max_keys=CTV_MAX_KEYS,
        ctv_max_days=CTV_MAX_DAYS,
        lookup=None,
        fmt=fmt_time,
    )


# ---------------- WEB ACTIONS ----------------


@app.route("/web/addctv", methods=["POST"])
@require_auth
def web_addctv():
    user_id = request.form.get("user_id", "").strip()
    if not user_id:
        return redirect(url_for("web_index"))
    name = request.form.get("name", "").strip() or None
    max_keys = int(request.form.get("max_keys", CTV_MAX_KEYS))
    max_days = int(request.form.get("max_days", CTV_MAX_DAYS))
    add_ctv(user_id, name=name, max_keys=max_keys, max_days=max_days)
    return redirect(url_for("web_index"))


@app.route("/web/removectv", methods=["POST"])
@require_auth
def web_removectv():
    remove_ctv(request.form.get("user_id", "").strip())
    return redirect(url_for("web_index"))


@app.route("/web/toggle_ctv", methods=["POST"])
@require_auth
def web_toggle_ctv():
    toggle_ctv(request.form.get("user_id", "").strip())
    return redirect(url_for("web_index"))


@app.route("/web/create", methods=["POST"])
@require_auth
def web_create():
    days = int(request.form.get("days", 30))
    owner = request.form.get("owner", "unknown")
    max_dev = int(request.form.get("max_devices", DEFAULT_MAX_DEVICES))
    create_key(days, owner, max_dev)
    return redirect(url_for("web_index"))


@app.route("/web/issue", methods=["POST"])
@require_auth
def web_issue():
    user_id = request.form.get("user_id", "").strip()
    if not user_id:
        return redirect(url_for("web_index"))
    days = int(request.form.get("days", DEFAULT_DAYS))
    owner = request.form.get("owner", "").strip() or f"user_{user_id}"
    max_dev = int(request.form.get("max_devices", DEFAULT_MAX_DEVICES))
    get_or_create_key_for_user(user_id, owner=owner, days=days, max_devices=max_dev)
    return redirect(url_for("web_index"))


@app.route("/web/toggle_auto", methods=["POST"])
@require_auth
def web_toggle_auto():
    global AUTO_ISSUE_ENABLED
    AUTO_ISSUE_ENABLED = not AUTO_ISSUE_ENABLED
    append_log("toggle_auto", {"enabled": AUTO_ISSUE_ENABLED})
    return redirect(url_for("web_index"))


@app.route("/web/toggle_once", methods=["POST"])
@require_auth
def web_toggle_once():
    global AUTO_ISSUE_ONCE
    AUTO_ISSUE_ONCE = not AUTO_ISSUE_ONCE
    append_log("toggle_once", {"once": AUTO_ISSUE_ONCE})
    return redirect(url_for("web_index"))


@app.route("/web/lookup", methods=["POST"])
@require_auth
def web_lookup():
    user_id = request.form.get("user_id", "").strip()
    key = get_key_by_user(user_id)
    lookup = None
    if key:
        r = load_keys().get(key)
        if r:
            devices = load_devices().get(key, {})
            lookup = {
                "user_id": user_id,
                "key": key,
                "owner": r["owner"],
                "expiresAt": fmt_time(r["expiresAt"]),
                "daysLeft": get_days_left(key),
                "devicesUsed": len(devices),
                "maxDevices": r.get("maxDevices", DEFAULT_MAX_DEVICES),
            }

    keys_all = load_keys()
    devices_all = load_devices()
    blocked = load_blocked()
    users = load_users()
    ctv = load_ctv()
    logs = read_json(LOG_FILE, [])[-30:]
    logs.reverse()
    device_count = {k: len(v) for k, v in devices_all.items()}
    days_left = {k: get_days_left(k) for k in keys_all}
    blocked_keys = blocked.get("keys", {})
    total_devices = sum(device_count.values())
    total_blocked = len(blocked.get("keys", {})) + len(blocked.get("devices", {}))
    return render_template_string(
        DASHBOARD_HTML,
        now=fmt_time(now_ms()),
        keys=keys_all,
        users=users,
        ctv=ctv,
        device_count=device_count,
        days_left=days_left,
        blocked_keys=blocked_keys,
        blocked=blocked,
        logs=logs,
        total_keys=len(keys_all),
        total_users=len(users),
        total_ctv=len(ctv),
        total_devices=total_devices,
        total_blocked=total_blocked,
        auto_issue=AUTO_ISSUE_ENABLED,
        auto_once=AUTO_ISSUE_ONCE,
        default_days=DEFAULT_DAYS,
        default_max_devices=DEFAULT_MAX_DEVICES,
        ctv_max_keys=CTV_MAX_KEYS,
        ctv_max_days=CTV_MAX_DAYS,
        lookup=lookup,
        fmt=fmt_time,
    )


@app.route("/web/adddays", methods=["POST"])
@require_auth
def web_adddays():
    add_days(request.form.get("key", ""), int(request.form.get("days", 0)))
    return redirect(url_for("web_index"))


@app.route("/web/revoke", methods=["POST"])
@require_auth
def web_revoke():
    revoke_key(request.form.get("key", ""))
    return redirect(url_for("web_index"))


@app.route("/web/resetdev", methods=["POST"])
@require_auth
def web_resetdev():
    reset_devices(request.form.get("key", ""))
    return redirect(url_for("web_index"))


@app.route("/web/delete", methods=["POST"])
@require_auth
def web_delete():
    delete_key(request.form.get("key", ""))
    return redirect(url_for("web_index"))


@app.route("/web/blockdev", methods=["POST"])
@require_auth
def web_blockdev():
    block_device("", request.form.get("device_id", ""), request.form.get("reason", "manual"))
    return redirect(url_for("web_index"))


@app.route("/web/unblockdev", methods=["POST"])
@require_auth
def web_unblockdev():
    unblock_device(request.form.get("device_id", ""))
    return redirect(url_for("web_index"))


# ---------------- API JSON ----------------


@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({
        "ok": True,
        "service": "full-key-server",
        "status": "online",
        "time": fmt_time(now_ms()),
        "autoIssue": AUTO_ISSUE_ENABLED,
        "autoIssueOnce": AUTO_ISSUE_ONCE,
        "totalCtv": len(load_ctv()),
    })


@app.route("/api/issue", methods=["POST"])
def api_issue():
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id") or data.get("userId")
    device_id = data.get("device_id") or data.get("deviceId")
    dylibs = data.get("dylibs")

    if not user_id:
        return jsonify({"ok": False, "error": "missing_user_id"}), 400

    if not AUTO_ISSUE_ENABLED:
        return jsonify({"ok": False, "error": "auto_issue_disabled"}), 403

    if device_id and is_device_blocked(device_id):
        return jsonify({"ok": False, "error": "device_blocked"}), 403

    if dylibs is not None:
        dylib_result = check_dylib_list(dylibs)
        if dylib_result["injected"]:
            if device_id:
                block_device("", device_id, "dylib_injected")
            append_log("issue_blocked_dylib", {"user_id": user_id, "device": device_id, "blocked": dylib_result["blocked"]})
            return jsonify({"ok": False, "error": "dylib_injected", "detail": dylib_result}), 403
        if dylib_result["unknown"]:
            return jsonify({"ok": False, "error": "dylib_unknown", "detail": dylib_result}), 403

    owner = data.get("owner") or f"user_{user_id}"
    days = int(data.get("days", DEFAULT_DAYS))
    max_dev = int(data.get("max_devices", DEFAULT_MAX_DEVICES))

    result = get_or_create_key_for_user(user_id, owner=owner, days=days, max_devices=max_dev)
    key = result["key"]
    record = result["record"]

    if device_id:
        verify_key(key, device_id, get_client_ip(request), request.headers.get("User-Agent", "unknown"), None)

    return jsonify({
        "ok": True,
        "created": result["created"],
        "key": key,
        "owner": record["owner"],
        "expiresAt": record["expiresAt"],
        "expiresAtText": fmt_time(record["expiresAt"]),
        "signature": record["signature"],
        "daysLeft": get_days_left(key),
        "maxDevices": record.get("maxDevices", DEFAULT_MAX_DEVICES),
    })


@app.route("/api/verify", methods=["POST"])
def api_verify():
    data = request.get_json(force=True, silent=True) or {}
    key = data.get("key")
    device_id = data.get("device_id") or data.get("deviceId")
    dylibs = data.get("dylibs")
    if not key or not device_id:
        return jsonify({"ok": False, "error": "missing_params"}), 400
    ip = get_client_ip(request)
    ua = request.headers.get("User-Agent", "unknown")
    result = verify_key(key, device_id, ip, ua, dylibs)
    status = 200 if result["ok"] else 403
    return jsonify(result), status


@app.route("/api/verify_user", methods=["POST"])
def api_verify_user():
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id") or data.get("userId")
    device_id = data.get("device_id") or data.get("deviceId")
    dylibs = data.get("dylibs")

    if not user_id or not device_id:
        return jsonify({"ok": False, "error": "missing_params"}), 400

    if not AUTO_ISSUE_ENABLED:
        return jsonify({"ok": False, "error": "auto_issue_disabled"}), 403

    if is_device_blocked(device_id):
        return jsonify({"ok": False, "error": "device_blocked"}), 403

    if dylibs is not None:
        dylib_result = check_dylib_list(dylibs)
        if dylib_result["injected"]:
            block_device("", device_id, "dylib_injected")
            append_log("verify_user_blocked_dylib", {"user_id": user_id, "device": device_id})
            return jsonify({"ok": False, "error": "dylib_injected", "detail": dylib_result}), 403
        if dylib_result["unknown"]:
            return jsonify({"ok": False, "error": "dylib_unknown", "detail": dylib_result}), 403

    owner = data.get("owner") or f"user_{user_id}"
    days = int(data.get("days", DEFAULT_DAYS))
    max_dev = int(data.get("max_devices", DEFAULT_MAX_DEVICES))

    result = get_or_create_key_for_user(user_id, owner=owner, days=days, max_devices=max_dev)
    key = result["key"]

    vr = verify_key(key, device_id, get_client_ip(request), request.headers.get("User-Agent", "unknown"), None)
    if not vr["ok"]:
        return jsonify(vr), 403

    vr["created"] = result["created"]
    vr["key"] = key
    return jsonify(vr), 200


@app.route("/api/info", methods=["POST"])
def api_info():
    data = request.get_json(force=True, silent=True) or {}
    key = data.get("key")
    r = load_keys().get(key)
    if not r:
        return jsonify({"ok": False, "error": "key_not_found"}), 404
    devices = load_devices().get(key, {})
    return jsonify({
        "ok": True,
        "owner": r["owner"],
        "userId": r.get("userId"),
        "createdBy": r.get("createdBy"),
        "active": r["active"],
        "blocked": is_key_blocked(key),
        "expiresAt": r["expiresAt"],
        "expiresAtText": fmt_time(r["expiresAt"]),
        "daysLeft": get_days_left(key),
        "maxDevices": r.get("maxDevices", DEFAULT_MAX_DEVICES),
        "devicesUsed": len(devices),
        "createdAt": r["createdAt"],
    })


@app.route("/api/user", methods=["POST"])
def api_user():
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id") or data.get("userId")
    if not user_id:
        return jsonify({"ok": False, "error": "missing_user_id"}), 400
    key = get_key_by_user(user_id)
    if not key:
        return jsonify({"ok": False, "error": "user_not_found"}), 404
    r = load_keys().get(key)
    if not r:
        return jsonify({"ok": False, "error": "key_not_found"}), 404
    return jsonify({
        "ok": True,
        "userId": user_id,
        "key": key,
        "owner": r["owner"],
        "active": r["active"],
        "expiresAt": r["expiresAt"],
        "expiresAtText": fmt_time(r["expiresAt"]),
        "daysLeft": get_days_left(key),
        "maxDevices": r.get("maxDevices", DEFAULT_MAX_DEVICES),
        "devicesUsed": len(load_devices().get(key, {})),
    })


@app.route("/api/days", methods=["POST"])
def api_days():
    data = request.get_json(force=True, silent=True) or {}
    days = get_days_left(data.get("key"))
    if days is None:
        return jsonify({"ok": False, "error": "key_not_found"}), 404
    return jsonify({"ok": True, "daysLeft": days})


# ---------------- API CTV ----------------


@app.route("/api/ctv/list", methods=["GET"])
@require_admin_token
def api_ctv_list():
    return jsonify({"ok": True, "ctv": load_ctv()})


@app.route("/api/ctv/add", methods=["POST"])
@require_admin_token
def api_ctv_add():
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id") or data.get("userId")
    if not user_id:
        return jsonify({"ok": False, "error": "missing_user_id"}), 400
    add_ctv(
        user_id,
        name=data.get("name"),
        max_keys=data.get("max_keys"),
        max_days=data.get("max_days"),
    )
    return jsonify({"ok": True, "user_id": str(user_id)})


@app.route("/api/ctv/remove", methods=["POST"])
@require_admin_token
def api_ctv_remove():
    data = request.get_json(force=True, silent=True) or {}
    ok = remove_ctv(data.get("user_id") or data.get("userId"))
    return jsonify({"ok": ok})


@app.route("/api/ctv/toggle", methods=["POST"])
@require_admin_token
def api_ctv_toggle():
    data = request.get_json(force=True, silent=True) or {}
    r = toggle_ctv(data.get("user_id") or data.get("userId"))
    if r is None:
        return jsonify({"ok": False, "error": "ctv_not_found"}), 404
    return jsonify({"ok": True, "active": r})


@app.route("/api/create", methods=["POST"])
@require_admin_token
def api_create():
    data = request.get_json(force=True, silent=True) or {}
    days = int(data.get("days", 30))
    owner = str(data.get("owner", "unknown"))
    max_dev = int(data.get("max_devices", DEFAULT_MAX_DEVICES))
    user_id = data.get("user_id")
    key, exp, sig = create_key(days, owner, max_dev, user_id=user_id)
    return jsonify({
        "ok": True, "key": key, "owner": owner, "userId": user_id,
        "expiresAt": exp, "expiresAtText": fmt_time(exp),
        "signature": sig, "maxDevices": max_dev,
    })


@app.route("/api/adddays", methods=["POST"])
@require_admin_token
def api_adddays():
    data = request.get_json(force=True, silent=True) or {}
    new_exp = add_days(data.get("key"), int(data.get("days", 0)))
    if not new_exp:
        return jsonify({"ok": False, "error": "key_not_found"}), 404
    return jsonify({"ok": True, "expiresAt": new_exp, "expiresAtText": fmt_time(new_exp)})


@app.route("/api/setexp", methods=["POST"])
@require_admin_token
def api_setexp():
    data = request.get_json(force=True, silent=True) or {}
    new_exp = set_expiry(data.get("key"), int(data.get("days_from_now", 0)))
    if not new_exp:
        return jsonify({"ok": False, "error": "key_not_found"}), 404
    return jsonify({"ok": True, "expiresAt": new_exp, "expiresAtText": fmt_time(new_exp)})


@app.route("/api/revoke", methods=["POST"])
@require_admin_token
def api_revoke():
    data = request.get_json(force=True, silent=True) or {}
    return jsonify({"ok": revoke_key(data.get("key"))})


@app.route("/api/delete", methods=["POST"])
@require_admin_token
def api_delete():
    data = request.get_json(force=True, silent=True) or {}
    return jsonify({"ok": delete_key(data.get("key"))})


@app.route("/api/resetdev", methods=["POST"])
@require_admin_token
def api_resetdev():
    data = request.get_json(force=True, silent=True) or {}
    reset_devices(data.get("key"))
    return jsonify({"ok": True})


@app.route("/api/blockdev", methods=["POST"])
@require_admin_token
def api_blockdev():
    data = request.get_json(force=True, silent=True) or {}
    device_id = data.get("device_id")
    if not device_id:
        return jsonify({"ok": False, "error": "missing_params"}), 400
    block_device(data.get("key", ""), device_id, data.get("reason", "manual"))
    return jsonify({"ok": True})


@app.route("/api/unblockdev", methods=["POST"])
@require_admin_token
def api_unblockdev():
    data = request.get_json(force=True, silent=True) or {}
    return jsonify({"ok": unblock_device(data.get("device_id"))})


@app.route("/api/blockkey", methods=["POST"])
@require_admin_token
def api_blockkey():
    data = request.get_json(force=True, silent=True) or {}
    block_key(data.get("key"), data.get("reason", "manual"))
    return jsonify({"ok": True})


@app.route("/api/unblockkey", methods=["POST"])
@require_admin_token
def api_unblockkey():
    data = request.get_json(force=True, silent=True) or {}
    return jsonify({"ok": unblock_key(data.get("key"))})


@app.route("/api/blocklist", methods=["GET"])
@require_admin_token
def api_blocklist():
    return jsonify({"ok": True, "blocked": load_blocked()})


@app.route("/api/checkdylib", methods=["POST"])
def api_checkdylib():
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(check_dylib_list(data.get("dylibs", [])))


@app.route("/api/list", methods=["GET"])
@require_admin_token
def api_list():
    return jsonify({"ok": True, "keys": load_keys()})


@app.route("/api/users", methods=["GET"])
@require_admin_token
def api_users():
    return jsonify({"ok": True, "users": load_users()})


@app.route("/api/devices", methods=["POST"])
@require_admin_token
def api_devices():
    data = request.get_json(force=True, silent=True) or {}
    return jsonify({"ok": True, "devices": load_devices().get(data.get("key"), {})})


@app.route("/api/logs", methods=["GET"])
@require_admin_token
def api_logs():
    n = int(request.args.get("n", 50))
    return jsonify({"ok": True, "logs": read_json(LOG_FILE, [])[-n:]})


@app.route("/api/stats", methods=["GET"])
@require_admin_token
def api_stats():
    keys = load_keys()
    devices = load_devices()
    blocked = load_blocked()
    users = load_users()
    ctv = load_ctv()
    return jsonify({
        "ok": True,
        "totalKeys": len(keys),
        "activeKeys": sum(1 for v in keys.values() if v.get("active")),
        "expiredKeys": sum(1 for v in keys.values() if now_ms() > v.get("expiresAt", 0)),
        "totalUsers": len(users),
        "totalCtv": len(ctv),
        "activeCtv": sum(1 for v in ctv.values() if v.get("active", True)),
        "totalDevices": sum(len(v) for v in devices.values()),
        "blockedKeys": len(blocked.get("keys", {})),
        "blockedDevices": len(blocked.get("devices", {})),
        "autoIssue": AUTO_ISSUE_ENABLED,
        "autoIssueOnce": AUTO_ISSUE_ONCE,
    })


# ---------------- TELEGRAM ----------------


def handle_update(update):
    msg = update.get("message")
    if not msg or "text" not in msg:
        return

    chat_id = msg["chat"]["id"]
    user_id = str(msg["from"]["id"])
    text = msg["text"].strip()
    parts = text.split()
    cmd = parts[0].lower()
    admin = is_admin(user_id)
    ctv = is_ctv(user_id)
    perm = admin or ctv

    if cmd == "/start":
        base = (
            "Key server đang hoạt động.\n"
            "/code - nhận key riêng cho bạn\n"
            "/mykey - xem key của bạn\n"
            "/verify &lt;key&gt; &lt;device_id&gt;\n"
            "/info &lt;key&gt;\n"
            "/days &lt;key&gt;\n"
        )
        if perm:
            base += (
                "/create &lt;days&gt; &lt;owner&gt; [max_devices]\n"
                "/issue &lt;user_id&gt; [days]\n"
                "/adddays &lt;key&gt; &lt;days&gt;\n"
                "/devices &lt;key&gt;\n"
            )
        if admin:
            base += (
                "/addctv &lt;user_id&gt; [name] [max_keys] [max_days]\n"
                "/removectv &lt;user_id&gt;\n"
                "/togglectv &lt;user_id&gt;\n"
                "/ctvlist\n"
                "/setexp &lt;key&gt; &lt;days_from_now&gt;\n"
                "/revoke &lt;key&gt;\n"
                "/resetdev &lt;key&gt;\n"
                "/delete &lt;key&gt;\n"
                "/blockdev &lt;device_id&gt; [reason]\n"
                "/unblockdev &lt;device_id&gt;\n"
                "/blockkey &lt;key&gt; [reason]\n"
                "/unblockkey &lt;key&gt;\n"
                "/blocklist\n"
                "/checkdylib &lt;base64_json&gt;\n"
                "/list\n"
                "/logs [n]"
            )
        send_message(chat_id, base)
        return

    # /code
    if cmd == "/code":
        if not AUTO_ISSUE_ENABLED:
            send_message(chat_id, "Chức năng cấp key tự động đang tắt.")
            return
        result = get_or_create_key_for_user(user_id, owner=f"tg_{user_id}")
        key = result["key"]
        record = result["record"]
        if result["created"]:
            send_message(
                chat_id,
                f"Đã cấp key riêng cho bạn.\nKey: <code>{key}</code>\n"
                f"Chủ: {record['owner']}\nHạn: {fmt_time(record['expiresAt'])}\n"
                f"Còn: {get_days_left(key)} ngày\n"
                f"Giới hạn TB: {record.get('maxDevices', DEFAULT_MAX_DEVICES)}",
            )
        else:
            send_message(
                chat_id,
                f"Bạn đã có key.\nKey: <code>{key}</code>\n"
                f"Hạn: {fmt_time(record['expiresAt'])}\nCòn: {get_days_left(key)} ngày",
            )
        return

    # /mykey
    if cmd == "/mykey":
        key = get_key_by_user(user_id)
        if not key:
            send_message(chat_id, "Bạn chưa có key. Dùng /code để nhận.")
            return
        r = load_keys().get(key)
        if not r:
            send_message(chat_id, "Key không tồn tại.")
            return
        devices = load_devices().get(key, {})
        send_message(
            chat_id,
            f"Key của bạn: <code>{key}</code>\n"
            f"Trạng thái: {'ON' if r['active'] else 'OFF'}\n"
            f"Hết hạn: {fmt_time(r['expiresAt'])}\n"
            f"Còn: {get_days_left(key)} ngày\n"
            f"Thiết bị: {len(devices)}/{r.get('maxDevices', DEFAULT_MAX_DEVICES)}",
        )
        return

    if cmd == "/verify":
        if len(parts) < 3:
            send_message(chat_id, "Cú pháp: /verify <key> <device_id>")
            return
        result = verify_key(parts[1], parts[2], "telegram", f"user:{user_id}")
        if not result["ok"]:
            send_message(chat_id, f"Thất bại: {result['error']}")
            return
        send_message(
            chat_id,
            f"Hợp lệ.\nChủ: {result['owner']}\n"
            f"Hết hạn: {result['expiresAtText']}\n"
            f"Còn: {result['remainingDays']} ngày\n"
            f"Thiết bị: {result['devicesUsed']}/{result['maxDevices']}",
        )
        return

    if cmd == "/info":
        if len(parts) < 2:
            send_message(chat_id, "Cú pháp: /info <key>")
            return
        key = parts[1]
        r = load_keys().get(key)
        if not r:
            send_message(chat_id, "Key không tồn tại.")
            return
        devices = load_devices().get(key, {})
        send_message(
            chat_id,
            f"Key: <code>{key}</code>\nChủ: {r['owner']}\n"
            f"UserID: {r.get('userId') or '-'}\n"
            f"Tạo bởi: {r.get('createdBy') or '-'}\n"
            f"Trạng thái: {'ON' if r['active'] else 'OFF'}\n"
            f"Bị block: {'CÓ' if is_key_blocked(key) else 'KHÔNG'}\n"
            f"Hết hạn: {fmt_time(r['expiresAt'])}\n"
            f"Còn lại: {get_days_left(key)} ngày\n"
            f"Giới hạn TB: {r.get('maxDevices', DEFAULT_MAX_DEVICES)}\n"
            f"Đã dùng: {len(devices)} thiết bị\n"
            f"Tạo lúc: {fmt_time(r['createdAt'])}",
        )
        return

    if cmd == "/days":
        if len(parts) < 2:
            send_message(chat_id, "Cú pháp: /days <key>")
            return
        days = get_days_left(parts[1])
        send_message(chat_id, "Key không tồn tại." if days is None else f"Còn lại: {days} ngày.")
        return

    # ---------- QUYEN CTV + ADMIN ----------

    if cmd == "/devices":
        if not perm:
            send_message(chat_id, "Không có quyền.")
            return
        if len(parts) < 2:
            send_message(chat_id, "Cú pháp: /devices <key>")
            return
        devices = load_devices().get(parts[1], {})
        if not devices:
            send_message(chat_id, "Chưa có thiết bị nào.")
            return
        lines = []
        for dev_id, info in devices.items():
            blk = " [BLOCKED]" if is_device_blocked(dev_id) else ""
            lines.append(
                f"<code>{dev_id}</code>{blk}\n  IP: {info.get('ip')}\n"
                f"  Lần đầu: {fmt_time(info['firstSeen'])}\n"
                f"  Lần cuối: {fmt_time(info['lastSeen'])}\n"
                f"  Số lần: {info.get('count', 0)}"
            )
        send_message(chat_id, "\n".join(lines))
        return

    if cmd == "/create":
        if not perm:
            send_message(chat_id, "Không có quyền.")
            return
        days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 30
        owner = parts[2] if len(parts) > 2 else "unknown"
        max_dev = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else DEFAULT_MAX_DEVICES
        # CTV gioi han
        if ctv and not admin:
            ok, err = ctv_can_create(user_id, days=days)
            if not ok:
                send_message(chat_id, f"Không thể tạo: {err}")
                return
        key, exp, sig = create_key(days, owner, max_dev, created_by=user_id if ctv else None)
        send_message(
            chat_id,
            f"Key mới:\n<code>{key}</code>\nChủ: {owner}\n"
            f"Hạn: {days} ngày ({fmt_time(exp)})\n"
            f"Giới hạn TB: {max_dev}\nChữ ký: <code>{sig}</code>",
        )
        return

    if cmd == "/issue":
        if not perm:
            send_message(chat_id, "Không có quyền.")
            return
        if len(parts) < 2:
            send_message(chat_id, "Cú pháp: /issue <user_id> [days]")
            return
        target = parts[1]
        days = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else DEFAULT_DAYS
        if ctv and not admin:
            ok, err = ctv_can_create(user_id, days=days)
            if not ok:
                send_message(chat_id, f"Không thể cấp: {err}")
                return
        result = get_or_create_key_for_user(target, owner=f"user_{target}", days=days, created_by=user_id if ctv else None)
        key = result["key"]
        record = result["record"]
        send_message(
            chat_id,
            f"{'Đã tạo' if result['created'] else 'Đã có'} key cho user {target}:\n"
            f"<code>{key}</code>\nHạn: {fmt_time(record['expiresAt'])}\n"
            f"Còn: {get_days_left(key)} ngày",
        )
        return

    if cmd == "/adddays":
        if not perm:
            send_message(chat_id, "Không có quyền.")
            return
        if len(parts) < 3 or not parts[2].lstrip("-").isdigit():
            send_message(chat_id, "Cú pháp: /adddays <key> <days>")
            return
        new_exp = add_days(parts[1], int(parts[2]))
        send_message(chat_id, "Key không tồn tại." if not new_exp else f"Đã cộng. Hết hạn mới: {fmt_time(new_exp)}")
        return

    # ---------- QUYEN ADMIN ----------

    if cmd == "/setexp":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        if len(parts) < 3 or not parts[2].isdigit():
            send_message(chat_id, "Cú pháp: /setexp <key> <days_from_now>")
            return
        new_exp = set_expiry(parts[1], int(parts[2]))
        send_message(chat_id, "Key không tồn tại." if not new_exp else f"Đã đặt hạn: {fmt_time(new_exp)}")
        return

    if cmd == "/revoke":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        ok = revoke_key(parts[1]) if len(parts) > 1 else False
        send_message(chat_id, "Đã vô hiệu hóa." if ok else "Key không tồn tại.")
        return

    if cmd == "/resetdev":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        reset_devices(parts[1]) if len(parts) > 1 else None
        send_message(chat_id, "Đã xóa danh sách thiết bị.")
        return

    if cmd == "/delete":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        ok = delete_key(parts[1]) if len(parts) > 1 else False
        send_message(chat_id, "Đã xóa." if ok else "Key không tồn tại.")
        return

    # ---------- QUAN LY CTV ----------

    if cmd == "/addctv":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        if len(parts) < 2:
            send_message(chat_id, "Cú pháp: /addctv <user_id> [name] [max_keys] [max_days]")
            return
        target = parts[1]
        name = parts[2] if len(parts) > 2 else None
        max_keys = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else CTV_MAX_KEYS
        max_days = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else CTV_MAX_DAYS
        add_ctv(target, name=name, max_keys=max_keys, max_days=max_days)
        send_message(
            chat_id,
            f"Đã thêm CTV: {target}\nTên: {name or f'ctv_{target}'}\n"
            f"Max keys: {max_keys}\nMax days: {max_days}",
        )
        return

    if cmd == "/removectv":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        if len(parts) < 2:
            send_message(chat_id, "Cú pháp: /removectv <user_id>")
            return
        ok = remove_ctv(parts[1])
        send_message(chat_id, "Đã xóa CTV." if ok else "Không tìm thấy CTV.")
        return

    if cmd == "/togglectv":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        if len(parts) < 2:
            send_message(chat_id, "Cú pháp: /togglectv <user_id>")
            return
        r = toggle_ctv(parts[1])
        if r is None:
            send_message(chat_id, "Không tìm thấy CTV.")
            return
        send_message(chat_id, f"CTV {parts[1]} hiện: {'ON' if r else 'OFF'}")
        return

    if cmd == "/ctvlist":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        ctv = load_ctv()
        if not ctv:
            send_message(chat_id, "Chưa có CTV nào.")
            return
        lines = []
        for uid, rec in ctv.items():
            lines.append(
                f"<code>{uid}</code> | {rec.get('name')} | "
                f"{'ON' if rec.get('active', True) else 'OFF'} | "
                f"{rec.get('keysCreated', 0)}/{rec.get('maxKeys')} key | "
                f"max {rec.get('maxDays')}d"
            )
        send_message(chat_id, "\n".join(lines))
        return

    if cmd == "/blockdev":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        if len(parts) < 2:
            send_message(chat_id, "Cú pháp: /blockdev <device_id> [reason]")
            return
        block_device("", parts[1], " ".join(parts[2:]) or "manual")
        send_message(chat_id, f"Đã block thiết bị: {parts[1]}")
        return

    if cmd == "/unblockdev":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        ok = unblock_device(parts[1]) if len(parts) > 1 else False
        send_message(chat_id, "Đã bỏ block." if ok else "Không có trong block list.")
        return

    if cmd == "/blockkey":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        if len(parts) < 2:
            send_message(chat_id, "Cú pháp: /blockkey <key> [reason]")
            return
        block_key(parts[1], " ".join(parts[2:]) or "manual")
        send_message(chat_id, f"Đã block key: {parts[1]}")
        return

    if cmd == "/unblockkey":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        ok = unblock_key(parts[1]) if len(parts) > 1 else False
        send_message(chat_id, "Đã bỏ block." if ok else "Không có trong block list.")
        return

    if cmd == "/blocklist":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        b = load_blocked()
        lines = ["=== KEY ==="]
        for k, v in b.get("keys", {}).items():
            lines.append(f"{k} | {v['reason']} | {fmt_time(v['time'])}")
        lines.append("=== DEVICE ===")
        for d, v in b.get("devices", {}).items():
            lines.append(f"{d} | {v.get('key','')} | {v['reason']} | {fmt_time(v['time'])}")
        send_message(chat_id, "\n".join(lines))
        return

    if cmd == "/checkdylib":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        if len(parts) < 2:
            send_message(chat_id, "Cú pháp: /checkdylib <base64_json>")
            return
        try:
            payload = base64.b64decode(parts[1]).decode("utf-8")
            dylibs = json.loads(payload)
            result = check_dylib_list(dylibs)
            send_message(
                chat_id,
                f"OK: {result['ok']}\nInjected: {result['injected']}\n"
                f"Blocked: {json.dumps(result['blocked'], ensure_ascii=False)}\n"
                f"Unknown: {json.dumps(result['unknown'], ensure_ascii=False)}",
            )
        except Exception as e:
            send_message(chat_id, f"Lỗi phân tích: {e}")
        return

    if cmd == "/list":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        keys = load_keys()
        if not keys:
            send_message(chat_id, "Chưa có key nào.")
            return
        lines = []
        for k, v in keys.items():
            status = "ON" if v["active"] else "OFF"
            dev_count = len(load_devices().get(k, {}))
            blk = "B" if is_key_blocked(k) else "-"
            lines.append(
                f"<code>{k}</code> | {v['owner']} | {v.get('userId') or '-'} | "
                f"by {v.get('createdBy') or '-'} | {status} | {blk} | "
                f"TB {dev_count}/{v.get('maxDevices', DEFAULT_MAX_DEVICES)} | "
                f"{get_days_left(k)}d | {fmt_time(v['expiresAt'])}"
            )
        send_message(chat_id, "\n".join(lines))
        return

    if cmd == "/logs":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 20
        logs = read_json(LOG_FILE, [])[-n:]
        if not logs:
            send_message(chat_id, "Chưa có log.")
            return
        lines = [f"{l['time']} | {l['event']} | {json.dumps(l['data'], ensure_ascii=False)}" for l in logs]
        send_message(chat_id, "\n".join(lines))
        return


@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        handle_update(request.get_json(force=True))
    except Exception as e:
        print("Lỗi xử lý update:", e)
    return "OK", 200


# ---------------- STARTUP ----------------


def set_webhook():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        print("Thiếu RENDER_EXTERNAL_URL, bỏ qua đăng ký webhook.")
        return
    webhook_url = f"{url}/webhook/{BOT_TOKEN}"
    try:
        r = requests.get(f"{API}/setWebhook", params={"url": webhook_url}, timeout=10)
        print("Kết quả setWebhook:", r.json())
    except Exception as e:
        print("Lỗi setWebhook:", e)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    set_webhook()
    app.run(host="0.0.0.0", port=port)
