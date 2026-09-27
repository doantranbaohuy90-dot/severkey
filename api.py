# api.py - Blueprint API JSON
# Tác giả: MADE BY Bao Huy

import os
import json
import time
from functools import wraps
from datetime import datetime

from flask import (
    Blueprint, request, jsonify, g, current_app,
)

import key as keymod
import auth as authmod
import apikey
from db import (
    get_db, execute, fetchone, fetchall, insert, update, delete,
    now_ms, fmt_time, rows_to_list,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
DEFAULT_DAYS = getattr(keymod, "DEFAULT_DAYS", 30)
DEFAULT_MAX_DEVICES = getattr(keymod, "DEFAULT_MAX_DEVICES", 1)

# ---------------- TIỆN ÍCH ----------------

def get_client_ip(req):
    fwd = req.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return req.remote_addr or "unknown"


def ok(data=None, meta=None, status=200):
    body = {"ok": True}
    if data is not None:
        body["data"] = data
    if meta is not None:
        body["meta"] = meta
    return jsonify(body), status


def err(code, message, status=400, extra=None):
    body = {"ok": False, "error": {"code": code, "message": message}}
    if extra:
        body["error"]["details"] = extra
    return jsonify(body), status


def parse_json():
    return request.get_json(force=True, silent=True) or {}


def parse_int(value, default=0, min_v=None, max_v=None):
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    if min_v is not None and n < min_v:
        n = min_v
    if max_v is not None and n > max_v:
        n = max_v
    return n


def parse_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    if isinstance(value, (int, float)):
        return bool(value)
    return default


# ---------------- XÁC THỰC ----------------

def _extract_api_key():
    raw = request.headers.get("X-API-Key")
    if raw:
        return raw.strip()
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _extract_admin_token():
    return request.headers.get("X-Admin-Token")


def require_api_key(scope=None):
    """Yêu cầu API key hợp lệ. Nếu scope được chỉ định, kiểm tra quyền."""
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            raw = _extract_api_key()
            rec = apikey.verify_api_key(raw)
            if not rec:
                return err("invalid_api_key", "API key không hợp lệ hoặc bị khóa", 401)
            if scope and not apikey.has_scope(rec, scope):
                return err("insufficient_scope",
                           f"API key không có quyền '{scope}'", 403)
            g.api_client = rec
            g.api_client_name = rec.get("name", "unknown")
            return f(*args, **kwargs)
        return wrapper
    return deco


def require_admin_token(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = _extract_admin_token()
        if not ADMIN_TOKEN or token != ADMIN_TOKEN:
            return err("unauthorized", "Admin token không hợp lệ", 401)
        g.api_client_name = "admin_token"
        return f(*args, **kwargs)
    return wrapper


def require_any_auth(scope=None):
    """Chấp nhận API key hoặc admin token."""
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            token = _extract_admin_token()
            if ADMIN_TOKEN and token == ADMIN_TOKEN:
                g.api_client_name = "admin_token"
                return f(*args, **kwargs)
            raw = _extract_api_key()
            rec = apikey.verify_api_key(raw)
            if not rec:
                return err("unauthorized", "Cần API key hoặc admin token", 401)
            if scope and not apikey.has_scope(rec, scope):
                return err("insufficient_scope",
                           f"Không có quyền '{scope}'", 403)
            g.api_client = rec
            g.api_client_name = rec.get("name", "unknown")
            return f(*args, **kwargs)
        return wrapper
    return deco


# ---------------- MIDDLEWARE LOG ----------------

@api_bp.before_request
def _before():
    g._api_start = time.time()


@api_bp.after_request
def _after(resp):
    if request.path.startswith("/api"):
        duration = int((time.time() - getattr(g, "_api_start", time.time())) * 1000)
        client = getattr(g, "api_client_name", "anonymous")
        ip = get_client_ip(request)
        try:
            apikey.log_api_request(
                client, request.method, request.path,
                resp.status_code, ip, duration,
            )
        except Exception:
            pass
    return resp


# ---------------- HEALTH ----------------

@api_bp.route("/health", methods=["GET"])
def health():
    try:
        db_ok = fetchone("SELECT 1 AS x") is not None
    except Exception:
        db_ok = False
    return ok({
        "service": "key-server",
        "status": "online" if db_ok else "degraded",
        "db": db_ok,
        "time": fmt_time(now_ms()),
        "version": os.environ.get("APP_VERSION", "1.0.0"),
    })


# ---------------- VERIFY ----------------

@api_bp.route("/verify", methods=["POST"])
@require_api_key("verify")
def verify():
    data = parse_json()
    key = (data.get("key") or "").strip()
    device_id = (data.get("device_id") or data.get("deviceId") or "").strip()
    dylibs = data.get("dylibs")
    if not key or not device_id:
        return err("missing_params", "Thiếu 'key' hoặc 'device_id'", 400)
    ua = request.headers.get("User-Agent", "unknown")
    ip = get_client_ip(request)
    result = keymod.verify_key(key, device_id, ip, ua, dylibs)
    if not result.get("ok"):
        return err(result.get("error", "verify_failed"),
                   result.get("error", "Xác thực thất bại"),
                   403, extra=result)
    return ok(result)


# ---------------- INFO ----------------

@api_bp.route("/info", methods=["POST"])
@require_api_key("info")
def info():
    data = parse_json()
    key = (data.get("key") or "").strip()
    if not key:
        return err("missing_params", "Thiếu 'key'", 400)
    rec = keymod.get_key_info(key)
    if not rec:
        return err("key_not_found", "Không tìm thấy key", 404)
    return ok(rec)


@api_bp.route("/days", methods=["POST"])
@require_api_key("info")
def days():
    data = parse_json()
    key = (data.get("key") or "").strip()
    if not key:
        return err("missing_params", "Thiếu 'key'", 400)
    d = keymod.get_days_left(key)
    if d is None:
        return err("key_not_found", "Không tìm thấy key", 404)
    return ok({"key": key, "daysLeft": d})


# ---------------- TREE ----------------

@api_bp.route("/tree", methods=["GET"])
@require_api_key("info")
def tree():
    try:
        tree_view = keymod.build_tree_view()
        lines = keymod.render_tree_text(tree_view)
    except Exception as e:
        return err("tree_error", str(e), 500)
    return ok({"tree": tree_view, "text": lines})


# ---------------- STATS ----------------

@api_bp.route("/stats", methods=["GET"])
@require_any_auth()
def stats():
    keys = keymod.load_keys()
    devices = keymod.load_devices()
    blocked = keymod.load_blocked()
    accounts = authmod.load_accounts()
    s = {
        "totalKeys": len(keys),
        "activeKeys": sum(1 for v in keys.values() if v.get("active")),
        "expiredKeys": sum(1 for v in keys.values()
                           if now_ms() > v.get("expiresAt", 0)),
        "totalDevices": sum(len(v) for v in devices.values()),
        "totalUsers": len(accounts),
        "blockedKeys": len(blocked.get("keys", {})),
        "blockedDevices": len(blocked.get("devices", {})),
    }
    return ok(s)


# ---------------- KEYS CRUD ----------------

@api_bp.route("/v1/keys", methods=["GET"])
@require_any_auth("keys")
def list_keys():
    page = parse_int(request.args.get("page", 1), 1, 1)
    limit = parse_int(request.args.get("limit", 20), 20, 1, 100)
    owner = request.args.get("owner")
    active = request.args.get("active")
    offset = (page - 1) * limit

    where = []
    params = []
    if owner:
        where.append("owner = ?")
        params.append(owner)
    if active is not None:
        where.append("active = ?")
        params.append(1 if parse_bool(active) else 0)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total_row = fetchone(f"SELECT COUNT(*) AS c FROM keys {where_sql}", tuple(params))
    total = total_row["c"] if total_row else 0

    rows = fetchall(
        f"""SELECT * FROM keys {where_sql}
            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        tuple(params) + (limit, offset),
    )
    now = now_ms()
    items = []
    for r in rows:
        days_left = max(0, int((r["expires_at"] - now) / 86400000))
        items.append({
            "key": r["key"],
            "owner": r["owner"],
            "userId": r["user_id"],
            "createdBy": r["created_by"],
            "parent": r["parent"],
            "maxDevices": r["max_devices"],
            "active": bool(r["active"]),
            "blocked": bool(r["blocked"]),
            "expiresAt": r["expires_at"],
            "expiresAtText": fmt_time(r["expires_at"]),
            "createdAt": r["created_at"],
            "daysLeft": days_left,
        })
    return ok(items, meta={"page": page, "limit": limit, "total": total})


@api_bp.route("/v1/keys/<key>", methods=["GET"])
@require_any_auth("keys")
def get_key(key):
    rec = keymod.get_key_info(key)
    if not rec:
        return err("key_not_found", "Không tìm thấy key", 404)
    return ok(rec)


@api_bp.route("/v1/keys", methods=["POST"])
@require_any_auth("keys")
def create_key():
    data = parse_json()
    days = parse_int(data.get("days", DEFAULT_DAYS), DEFAULT_DAYS, 1, 3650)
    owner = (data.get("owner") or "api_client").strip()
    max_dev = parse_int(data.get("max_devices", DEFAULT_MAX_DEVICES),
                        DEFAULT_MAX_DEVICES, 1, 1000)
    parent = data.get("parent")
    user_id = data.get("user_id")
    created_by = getattr(g, "api_client_name", "api")

    try:
        k, exp, sig = keymod.create_key(
            days, owner, max_dev, user_id=user_id,
            created_by=created_by, parent_key=parent,
        )
    except Exception as e:
        return err("create_failed", str(e), 500)

    return ok({
        "key": k,
        "owner": owner,
        "days": days,
        "maxDevices": max_dev,
        "expiresAt": exp,
        "expiresAtText": fmt_time(exp),
        "signature": sig,
        "parent": parent,
    }, status=201)


@api_bp.route("/v1/keys/<key>/adddays", methods=["POST"])
@require_any_auth("keys")
def add_days(key):
    data = parse_json()
    days = parse_int(data.get("days", 0), 0, -3650, 3650)
    if days == 0:
        return err("invalid_days", "Số ngày phải khác 0", 400)
    new_exp = keymod.add_days(key, days)
    if not new_exp:
        return err("key_not_found", "Không tìm thấy key", 404)
    return ok({"key": key, "daysAdded": days,
               "expiresAt": new_exp, "expiresAtText": fmt_time(new_exp)})


@api_bp.route("/v1/keys/<key>/revoke", methods=["POST"])
@require_any_auth("keys")
def revoke_key(key):
    keymod.revoke_key(key)
    return ok({"key": key, "revoked": True})


@api_bp.route("/v1/keys/<key>/reset", methods=["POST"])
@require_any_auth("keys")
def reset_devices(key):
    keymod.reset_devices(key)
    return ok({"key": key, "reset": True})


@api_bp.route("/v1/keys/<key>", methods=["DELETE"])
@require_any_auth("keys")
def delete_key(key):
    keymod.delete_key(key)
    return ok({"key": key, "deleted": True})


# ---------------- DEVICES ----------------

@api_bp.route("/v1/devices", methods=["GET"])
@require_any_auth("devices")
def list_devices():
    page = parse_int(request.args.get("page", 1), 1, 1)
    limit = parse_int(request.args.get("limit", 50), 50, 1, 200)
    key = request.args.get("key")
    offset = (page - 1) * limit

    where = []
    params = []
    if key:
        where.append("key = ?")
        params.append(key)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total_row = fetchone(f"SELECT COUNT(*) AS c FROM devices {where_sql}",
                         tuple(params))
    total = total_row["c"] if total_row else 0

    rows = fetchall(
        f"""SELECT d.*,
                  (SELECT 1 FROM blocked b
                   WHERE b.type='device' AND b.id=d.device_id) AS blocked
            FROM devices d {where_sql}
            ORDER BY last_seen DESC LIMIT ? OFFSET ?""",
        tuple(params) + (limit, offset),
    )
    items = [{
        "deviceId": r["device_id"],
        "key": r["key"],
        "ip": r["ip"],
        "userAgent": r["user_agent"],
        "firstSeen": r["first_seen"],
        "firstSeenText": fmt_time(r["first_seen"]),
        "lastSeen": r["last_seen"],
        "lastSeenText": fmt_time(r["last_seen"]),
        "count": r["count"],
        "blocked": bool(r["blocked"]),
    } for r in rows]
    return ok(items, meta={"page": page, "limit": limit, "total": total})


@api_bp.route("/v1/devices/<device_id>", methods=["GET"])
@require_any_auth("devices")
def get_device(device_id):
    row = fetchone("SELECT * FROM devices WHERE device_id = ?", (device_id,))
    if not row:
        return err("device_not_found", "Không tìm thấy thiết bị", 404)
    rec = dict(row)
    rec["blocked"] = keymod.is_device_blocked(device_id)
    rec["firstSeenText"] = fmt_time(rec.get("first_seen", 0))
    rec["lastSeenText"] = fmt_time(rec.get("last_seen", 0))
    return ok(rec)


@api_bp.route("/v1/devices/<device_id>/block", methods=["POST"])
@require_any_auth("blocks")
def block_device(device_id):
    data = parse_json()
    reason = data.get("reason", "api_block")
    key = data.get("key", "")
    keymod.block_device(key, device_id, reason)
    return ok({"deviceId": device_id, "blocked": True, "reason": reason})


@api_bp.route("/v1/devices/<device_id>/unblock", methods=["POST"])
@require_any_auth("blocks")
def unblock_device(device_id):
    keymod.unblock_device(device_id)
    return ok({"deviceId": device_id, "blocked": False})


# ---------------- BLOCKS ----------------

@api_bp.route("/v1/blocks", methods=["GET"])
@require_any_auth("blocks")
def list_blocks():
    rows = fetchall("SELECT * FROM blocked ORDER BY time DESC LIMIT 500")
    items = [{
        "type": r["type"],
        "id": r["id"],
        "key": r["key"],
        "reason": r["reason"],
        "time": r["time"],
        "timeText": fmt_time(r["time"]),
    } for r in rows]
    return ok(items)


@api_bp.route("/v1/blocks/key", methods=["POST"])
@require_any_auth("blocks")
def block_key():
    data = parse_json()
    key = (data.get("key") or "").strip()
    reason = data.get("reason", "api_block")
    if not key:
        return err("missing_params", "Thiếu 'key'", 400)
    keymod.block_key(key, reason)
    return ok({"key": key, "blocked": True, "reason": reason})


@api_bp.route("/v1/blocks/key/<key>", methods=["DELETE"])
@require_any_auth("blocks")
def unblock_key(key):
    keymod.unblock_key(key)
    return ok({"key": key, "blocked": False})


# ---------------- CTV ----------------

@api_bp.route("/v1/ctv", methods=["GET"])
@require_any_auth("ctv")
def list_ctv():
    rows = fetchall("SELECT * FROM ctv ORDER BY added_at DESC")
    items = [{
        "userId": r["user_id"],
        "name": r["name"],
        "maxKeys": r["max_keys"],
        "maxDays": r["max_days"],
        "keysCreated": r["keys_created"],
        "active": bool(r["active"]),
        "addedAt": r["added_at"],
        "addedAtText": fmt_time(r["added_at"]),
    } for r in rows]
    return ok(items)


@api_bp.route("/v1/ctv", methods=["POST"])
@require_any_auth("ctv")
def create_ctv():
    data = parse_json()
    user_id = (data.get("user_id") or "").strip()
    if not user_id:
        return err("missing_params", "Thiếu 'user_id'", 400)
    name = data.get("name") or f"ctv_{user_id}"
    max_keys = parse_int(data.get("max_keys", 50), 50, 1, 100000)
    max_days = parse_int(data.get("max_days", 30), 30, 1, 3650)

    existing = fetchone("SELECT user_id FROM ctv WHERE user_id = ?", (user_id,))
    if existing:
        update("ctv", {
            "name": name, "max_keys": max_keys, "max_days": max_days,
            "active": 1,
        }, "user_id = ?", (user_id,))
    else:
        insert("ctv", {
            "user_id": user_id, "name": name,
            "max_keys": max_keys, "max_days": max_days,
            "keys_created": 0, "added_at": now_ms(), "active": 1,
        })
    return ok({"userId": user_id, "name": name,
               "maxKeys": max_keys, "maxDays": max_days}, status=201)


@api_bp.route("/v1/ctv/<user_id>", methods=["DELETE"])
@require_any_auth("ctv")
def delete_ctv(user_id):
    execute("DELETE FROM ctv WHERE user_id = ?", (user_id,))
    return ok({"userId": user_id, "deleted": True})


@api_bp.route("/v1/ctv/<user_id>/toggle", methods=["POST"])
@require_any_auth("ctv")
def toggle_ctv(user_id):
    row = fetchone("SELECT active FROM ctv WHERE user_id = ?", (user_id,))
    if not row:
        return err("ctv_not_found", "Không tìm thấy CTV", 404)
    new_state = 0 if row["active"] else 1
    execute("UPDATE ctv SET active = ? WHERE user_id = ?", (new_state, user_id))
    return ok({"userId": user_id, "active": bool(new_state)})


# ---------------- LOGS ----------------

@api_bp.route("/v1/logs", methods=["GET"])
@require_any_auth("logs")
def list_logs():
    n = parse_int(request.args.get("n", 100), 100, 1, 1000)
    rows = fetchall("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (n,))
    items = [{
        "time": fmt_time(r["time"]),
        "event": r["event"],
        "data": r["data"],
        "uid": r["uid"],
        "ip": r["ip"],
    } for r in rows]
    return ok(items, meta={"count": len(items)})


@api_bp.route("/v1/api-logs", methods=["GET"])
@require_any_auth("logs")
def list_api_logs():
    n = parse_int(request.args.get("n", 100), 100, 1, 1000)
    return ok(apikey.list_api_logs(n))


# ---------------- API KEY ADMIN ----------------

@api_bp.route("/v1/apikeys", methods=["GET"])
@require_any_auth("admin")
def api_list_keys():
    return ok(apikey.list_api_keys())


@api_bp.route("/v1/apikeys", methods=["POST"])
@require_any_auth("admin")
def api_create_key():
    data = parse_json()
    name = (data.get("name") or "client").strip()
    scopes = data.get("scopes") or ["verify", "info"]
    role = data.get("role", "client")
    rate = parse_int(data.get("rate_limit", 60), 60, 1, 100000)
    raw = apikey.create_api_key(name, scopes, role, rate,
                                created_by=getattr(g, "api_client_name", None))
    if not raw:
        return err("create_failed", "Không tạo được API key", 500)
    return ok({"name": name, "rawKey": raw,
               "note": "Lưu lại ngay, không hiển thị lại."}, status=201)


@api_bp.route("/v1/apikeys/<hashed>/toggle", methods=["POST"])
@require_any_auth("admin")
def api_toggle_key(hashed):
    state = apikey.toggle_api_key(hashed)
    if state is None:
        return err("apikey_not_found", "Không tìm thấy API key", 404)
    return ok({"hash": hashed, "active": state})


@api_bp.route("/v1/apikeys/<hashed>/rotate", methods=["POST"])
@require_any_auth("admin")
def api_rotate_key(hashed):
    raw = apikey.rotate_api_key(hashed)
    if not raw:
        return err("apikey_not_found", "Không tìm thấy API key", 404)
    return ok({"hash": hashed, "rawKey": raw,
               "note": "Lưu lại ngay."})


@api_bp.route("/v1/apikeys/<hashed>", methods=["DELETE"])
@require_any_auth("admin")
def api_delete_key(hashed):
    if not apikey.delete_api_key(hashed):
        return err("apikey_not_found", "Không tìm thấy API key", 404)
    return ok({"hash": hashed, "deleted": True})


# ---------------- LỖI ----------------

@api_bp.errorhandler(404)
def api_404(e):
    return err("not_found", "Endpoint không tồn tại", 404)


@api_bp.errorhandler(405)
def api_405(e):
    return err("method_not_allowed", "Method không được hỗ trợ", 405)


@api_bp.errorhandler(500)
def api_500(e):
    return err("internal_error", "Lỗi hệ thống", 500)


# ---------------- ĐĂNG KÝ ----------------

def register(app):
    """Đăng ký blueprint API vào Flask app."""
    app.register_blueprint(api_bp)
    return api_bp
