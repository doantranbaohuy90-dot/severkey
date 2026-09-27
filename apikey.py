# apikey.py - Quản lý API key cho client tích hợp
# Tác giả: MADE BY Bao Huy
# Phụ thuộc: db.py

import os
import json
import time
import hmac
import hashlib
import secrets
from datetime import datetime

from db import (
    get_db, execute, fetchone, fetchall, insert, update, delete,
    now_ms, fmt_time, row_to_dict, rows_to_list,
)

# ============================================================
# CẤU HÌNH
# ============================================================

DEFAULT_SCOPES = ["verify", "info"]
DEFAULT_RATE_LIMIT = 60
PREFIX = os.environ.get("APIKEY_PREFIX", "ks")
MAX_KEYS = int(os.environ.get("APIKEY_MAX_KEYS", "1000"))

SCOPE_LIST = [
    "verify", "info", "keys", "devices",
    "blocks", "ctv", "logs", "admin",
]


# ============================================================
# TIỆN ÍCH NỘI BỘ
# ============================================================

def _hash(raw):
    """Băm SHA-256 của raw key."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _generate():
    """Sinh raw key ngẫu nhiên."""
    return f"{PREFIX}_{secrets.token_urlsafe(32)}"


def _preview(raw):
    """Tạo preview ngắn để hiển thị."""
    if not raw:
        return ""
    if len(raw) <= 12:
        return raw
    return raw[:8] + "..." + raw[-4:]


def _parse_scopes(scopes):
    """Chuẩn hóa scopes thành list."""
    if scopes is None:
        return list(DEFAULT_SCOPES)
    if isinstance(scopes, str):
        return [s.strip() for s in scopes.split(",") if s.strip()]
    return [str(s).strip() for s in scopes if str(s).strip()]


def _validate_scopes(scopes):
    """Loại bỏ scope không hợp lệ."""
    valid = []
    for s in scopes:
        if s in SCOPE_LIST:
            valid.append(s)
    return valid or list(DEFAULT_SCOPES)


def _log(event, data=None, uid=None, ip=None):
    """Ghi log vào bảng logs."""
    try:
        execute(
            "INSERT INTO logs (time, event, data, uid, ip) VALUES (?, ?, ?, ?, ?)",
            (now_ms(), event,
             json.dumps(data or {}, ensure_ascii=False),
             uid, ip),
        )
    except Exception as e:
        print(f"[APIKEY] log lỗi: {e}")


# ============================================================
# TẠO / XÓA / XOAY API KEY
# ============================================================

def create_api_key(name, scopes=None, role="client",
                    rate_limit=DEFAULT_RATE_LIMIT,
                    created_by=None, expires_at=None):
    """
    Tạo API key mới.
    Trả raw key (chỉ hiển thị một lần) hoặc None nếu lỗi.
    """
    if count_total() >= MAX_KEYS:
        print(f"[APIKEY] Đã đạt giới hạn {MAX_KEYS} key")
        return None

    raw = _generate()
    hashed = _hash(raw)
    scopes_list = _validate_scopes(_parse_scopes(scopes))

    data = {
        "hash": hashed,
        "name": name or "client",
        "scopes": json.dumps(scopes_list, ensure_ascii=False),
        "role": role,
        "rate_limit": int(rate_limit),
        "usage_count": 0,
        "active": 1,
        "created_at": now_ms(),
        "last_used_at": None,
        "preview": _preview(raw),
    }
    if expires_at:
        data["expires_at"] = int(expires_at)

    try:
        insert("api_keys", data)
    except Exception as e:
        print(f"[APIKEY] create lỗi: {e}")
        return None

    _log("apikey_create", {
        "name": name, "role": role,
        "scopes": scopes_list, "preview": data["preview"],
    }, uid=created_by)
    return raw


def verify_api_key(raw):
    """
    Xác thực API key.
    Trả dict record nếu hợp lệ, None nếu không.
    Tự động tăng usage_count và cập nhật last_used_at.
    """
    if not raw:
        return None
    hashed = _hash(raw)
    row = fetchone("SELECT * FROM api_keys WHERE hash = ?", (hashed,))
    if not row:
        return None
    rec = dict(row)
    if not rec.get("active"):
        return None
    if rec.get("expires_at") and now_ms() > rec["expires_at"]:
        return None
    try:
        execute(
            "UPDATE api_keys SET usage_count = usage_count + 1, "
            "last_used_at = ? WHERE hash = ?",
            (now_ms(), hashed),
        )
    except Exception:
        pass
    try:
        rec["scopes"] = json.loads(rec.get("scopes") or "[]")
    except Exception:
        rec["scopes"] = []
    return rec


def has_scope(rec, scope):
    """Kiểm tra record có scope yêu cầu không."""
    if not rec:
        return False
    if rec.get("role") == "admin":
        return True
    return scope in rec.get("scopes", [])


def get_api_key(hashed):
    """Lấy record theo hash."""
    row = fetchone("SELECT * FROM api_keys WHERE hash = ?", (hashed,))
    if not row:
        return None
    rec = dict(row)
    try:
        rec["scopes"] = json.loads(rec.get("scopes") or "[]")
    except Exception:
        rec["scopes"] = []
    return rec


def toggle_api_key(hashed):
    """Bật/tắt API key. Trả trạng thái mới hoặc None."""
    rec = get_api_key(hashed)
    if not rec:
        return None
    new_state = 0 if rec.get("active") else 1
    execute("UPDATE api_keys SET active = ? WHERE hash = ?",
            (new_state, hashed))
    _log("apikey_toggle", {"hash": hashed, "active": new_state})
    return bool(new_state)


def rotate_api_key(hashed):
    """Tạo raw key mới cho cùng record. Trả raw mới."""
    rec = get_api_key(hashed)
    if not rec:
        return None
    raw = _generate()
    new_hash = _hash(raw)
    execute(
        """UPDATE api_keys
           SET hash = ?, preview = ?, created_at = ?,
               last_used_at = NULL, usage_count = 0
           WHERE hash = ?""",
        (new_hash, _preview(raw), now_ms(), hashed),
    )
    _log("apikey_rotate", {"name": rec.get("name"), "old": hashed[:12]})
    return raw


def delete_api_key(hashed):
    """Xóa API key. Trả True/False."""
    rec = get_api_key(hashed)
    if not rec:
        return False
    execute("DELETE FROM api_keys WHERE hash = ?", (hashed,))
    _log("apikey_delete", {"name": rec.get("name")})
    return True


def rename_api_key(hashed, new_name):
    """Đổi tên API key."""
    rec = get_api_key(hashed)
    if not rec:
        return False
    execute("UPDATE api_keys SET name = ? WHERE hash = ?", (new_name, hashed))
    return True


def update_rate_limit(hashed, rate_limit):
    """Cập nhật rate limit."""
    return execute(
        "UPDATE api_keys SET rate_limit = ? WHERE hash = ?",
        (int(rate_limit), hashed),
    ).rowcount > 0


def update_scopes(hashed, scopes):
    """Cập nhật scopes."""
    scopes_list = _validate_scopes(_parse_scopes(scopes))
    return execute(
        "UPDATE api_keys SET scopes = ? WHERE hash = ?",
        (json.dumps(scopes_list, ensure_ascii=False), hashed),
    ).rowcount > 0


# ============================================================
# TRUY VẤN
# ============================================================

def list_api_keys(limit=200, offset=0, active_only=False):
    """Danh sách API key đã format cho UI."""
    query = "SELECT * FROM api_keys"
    params = []
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = fetchall(query, tuple(params))
    items = []
    for r in rows:
        rec = dict(r)
        try:
            scopes = json.loads(rec.get("scopes") or "[]")
        except Exception:
            scopes = []
        items.append({
            "key": rec["hash"],
            "keyPreview": rec.get("preview", "???"),
            "name": rec.get("name", ""),
            "scopes": scopes,
            "scopesText": ", ".join(scopes),
            "role": rec.get("role", "client"),
            "rateLimit": rec.get("rate_limit", DEFAULT_RATE_LIMIT),
            "usageCount": rec.get("usage_count", 0),
            "active": bool(rec.get("active")),
            "createdAtText": fmt_time(rec.get("created_at", 0)),
            "lastUsedText": fmt_time(rec.get("last_used_at"))
                if rec.get("last_used_at") else "-",
            "expiresAt": rec.get("expires_at"),
        })
    return items


def count_total():
    """Tổng số API key."""
    row = fetchone("SELECT COUNT(*) AS c FROM api_keys")
    return row["c"] if row else 0


def count_active():
    """Số API key đang hoạt động."""
    row = fetchone("SELECT COUNT(*) AS c FROM api_keys WHERE active = 1")
    return row["c"] if row else 0


def find_by_name(name):
    """Tìm API key theo tên."""
    rows = fetchall("SELECT * FROM api_keys WHERE name = ?", (name,))
    return [dict(r) for r in rows]


# ============================================================
# LOG API REQUEST
# ============================================================

def log_api_request(client, method, path, status, ip, duration):
    """Ghi log mỗi request API."""
    try:
        execute(
            """INSERT INTO api_logs
               (time, client, method, path, status, ip, duration)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (now_ms(), client or "anonymous", method, path,
             int(status), ip or "", int(duration)),
        )
    except Exception as e:
        print(f"[APIKEY] log_api lỗi: {e}")


def list_api_logs(limit=100, offset=0, client=None):
    """Danh sách log API đã format."""
    query = "SELECT * FROM api_logs"
    params = []
    if client:
        query += " WHERE client = ?"
        params.append(client)
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = fetchall(query, tuple(params))
    return [{
        "time": fmt_time(r["time"]),
        "timeMs": r["time"],
        "client": r["client"],
        "method": r["method"],
        "path": r["path"],
        "status": r["status"],
        "ip": r["ip"],
        "duration": r["duration"],
    } for r in rows]


def count_api_logs(client=None):
    if client:
        row = fetchone("SELECT COUNT(*) AS c FROM api_logs WHERE client = ?",
                       (client,))
    else:
        row = fetchone("SELECT COUNT(*) AS c FROM api_logs")
    return row["c"] if row else 0


def stats_api_logs(hours=24):
    """Thống kê log API trong N giờ."""
    since = now_ms() - hours * 3600000
    row = fetchone("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) AS failed,
            AVG(duration) AS avgDuration,
            MAX(duration) AS maxDuration,
            COUNT(DISTINCT client) AS clients
        FROM api_logs WHERE time > ?
    """, (since,))
    if not row:
        return {"total": 0, "failed": 0,
                "avgDuration": 0, "maxDuration": 0, "clients": 0}
    return {
        "total": row["total"] or 0,
        "failed": row["failed"] or 0,
        "avgDuration": int(row["avgDuration"] or 0),
        "maxDuration": int(row["maxDuration"] or 0),
        "clients": row["clients"] or 0,
    }


def cleanup_api_logs(keep=10000):
    """Giữ lại N bản ghi log mới nhất."""
    try:
        execute(
            """DELETE FROM api_logs
               WHERE id NOT IN (
                   SELECT id FROM api_logs ORDER BY id DESC LIMIT ?
               )""",
            (keep,),
        )
        return True
    except Exception as e:
        print(f"[APIKEY] cleanup lỗi: {e}")
        return False


# ============================================================
# RATE LIMIT ĐƠN GIẢN
# ============================================================

_rate_buckets = {}
_rate_lock = __import__("threading").Lock()


def check_rate_limit(hashed, rate_limit):
    """
    Kiểm tra rate limit theo cửa sổ 60 giây.
    Trả (allowed: bool, remaining: int).
    """
    import time as _t
    now = int(_t.time())
    window = now // 60

    with _rate_lock:
        key = (hashed, window)
        count = _rate_buckets.get(key, 0)
        if count >= rate_limit:
            return False, 0
        _rate_buckets[key] = count + 1

        # Dọn bucket cũ
        if len(_rate_buckets) > 10000:
            for k in list(_rate_buckets.keys()):
                if k[1] < window - 2:
                    del _rate_buckets[k]

        return True, rate_limit - count - 1


def reset_rate_limit():
    """Xóa toàn bộ bucket."""
    with _rate_lock:
        _rate_buckets.clear()


# ============================================================
# XUẤT / NHẬP
# ============================================================

def export_keys():
    """Xuất danh sách API key (không có raw)."""
    rows = fetchall("SELECT * FROM api_keys ORDER BY created_at")
    items = []
    for r in rows:
        rec = dict(r)
        try:
            rec["scopes"] = json.loads(rec.get("scopes") or "[]")
        except Exception:
            rec["scopes"] = []
        items.append(rec)
    return items


def import_keys(items):
    """Nhập danh sách API key từ dict."""
    count = 0
    for rec in items:
        try:
            insert_or_ignore = getattr(__import__("db"), "insert_or_ignore")
            insert_or_ignore("api_keys", {
                "hash": rec["hash"],
                "name": rec.get("name", ""),
                "scopes": json.dumps(rec.get("scopes", []), ensure_ascii=False),
                "role": rec.get("role", "client"),
                "rate_limit": rec.get("rate_limit", DEFAULT_RATE_LIMIT),
                "usage_count": rec.get("usage_count", 0),
                "active": 1 if rec.get("active") else 0,
                "created_at": rec.get("created_at", now_ms()),
                "last_used_at": rec.get("last_used_at"),
                "preview": rec.get("preview", ""),
            })
            count += 1
        except Exception as e:
            print(f"[APIKEY] import lỗi: {e}")
    return count
