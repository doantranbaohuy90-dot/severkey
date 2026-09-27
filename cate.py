# apikey.py - Quản lý API key cho client tích hợp
# Tác giả: MADE BY Bao Huy

import os
import time
import json
import hmac
import hashlib
import secrets
from datetime import datetime

from db import (
    get_db, execute, fetchone, fetchall, insert, update, delete,
    now_ms, fmt_time, row_to_dict, rows_to_list,
)

DEFAULT_SCOPES = ["verify", "info"]
DEFAULT_RATE_LIMIT = 60
PREFIX = os.environ.get("APIKEY_PREFIX", "ks")


def _hash(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _generate():
    return f"{PREFIX}_{secrets.token_urlsafe(32)}"


def _preview(raw):
    if len(raw) <= 12:
        return raw
    return raw[:8] + "..." + raw[-4:]


def _parse_scopes(scopes):
    if scopes is None:
        return DEFAULT_SCOPES
    if isinstance(scopes, str):
        return [s.strip() for s in scopes.split(",") if s.strip()]
    return list(scopes)


def create_api_key(name, scopes=None, role="client", rate_limit=DEFAULT_RATE_LIMIT,
                    created_by=None, expires_at=None):
    """Tạo API key mới, trả raw key (chỉ hiển thị 1 lần)."""
    raw = _generate()
    hashed = _hash(raw)
    scopes_list = _parse_scopes(scopes)
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
        data["expires_at"] = expires_at
    try:
        insert("api_keys", data)
    except Exception as e:
        print(f"[APIKEY] create lỗi: {e}")
        return None
    try:
        from db import insert as _ins
        _ins("logs", {
            "time": now_ms(),
            "event": "apikey_create",
            "data": json.dumps({"name": name, "role": role, "scopes": scopes_list},
                                ensure_ascii=False),
            "uid": created_by,
            "ip": None,
        })
    except Exception:
        pass
    return raw


def verify_api_key(raw):
    """Xác thực API key, trả record nếu hợp lệ."""
    if not raw:
        return None
    hashed = _hash(raw)
    row = fetchone("SELECT * FROM api_keys WHERE hash = ?", (hashed,))
    if not row:
        return None
    rec = dict(row)
    if not rec.get("active"):
        return None
    execute(
        "UPDATE api_keys SET usage_count = usage_count + 1, last_used_at = ? WHERE hash = ?",
        (now_ms(), hashed),
    )
    try:
        rec["scopes"] = json.loads(rec.get("scopes") or "[]")
    except Exception:
        rec["scopes"] = []
    return rec


def has_scope(rec, scope):
    if not rec:
        return False
    if rec.get("role") == "admin":
        return True
    return scope in rec.get("scopes", [])


def list_api_keys():
    rows = fetchall("SELECT * FROM api_keys ORDER BY created_at DESC")
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
        })
    return items


def get_api_key(hashed):
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
    rec = get_api_key(hashed)
    if not rec:
        return None
    new_state = 0 if rec["active"] else 1
    execute("UPDATE api_keys SET active = ? WHERE hash = ?", (new_state, hashed))
    return bool(new_state)


def rotate_api_key(hashed):
    """Tạo raw key mới cho cùng record, trả raw mới."""
    rec = get_api_key(hashed)
    if not rec:
        return None
    raw = _generate()
    new_hash = _hash(raw)
    execute(
        """UPDATE api_keys
           SET hash = ?, preview = ?, created_at = ?, last_used_at = NULL,
               usage_count = 0
           WHERE hash = ?""",
        (new_hash, _preview(raw), now_ms(), hashed),
    )
    try:
        execute(
            "INSERT INTO logs (time, event, data) VALUES (?, ?, ?)",
            (now_ms(), "apikey_rotate",
             json.dumps({"name": rec.get("name")}, ensure_ascii=False)),
        )
    except Exception:
        pass
    return raw


def delete_api_key(hashed):
    rec = get_api_key(hashed)
    if not rec:
        return False
    execute("DELETE FROM api_keys WHERE hash = ?", (hashed,))
    try:
        execute(
            "INSERT INTO logs (time, event, data) VALUES (?, ?, ?)",
            (now_ms(), "apikey_delete",
             json.dumps({"name": rec.get("name")}, ensure_ascii=False)),
        )
    except Exception:
        pass
    return True


def update_rate_limit(hashed, rate_limit):
    return execute("UPDATE api_keys SET rate_limit = ? WHERE hash = ?",
                   (int(rate_limit), hashed))


def update_scopes(hashed, scopes):
    scopes_list = _parse_scopes(scopes)
    return execute("UPDATE api_keys SET scopes = ? WHERE hash = ?",
                   (json.dumps(scopes_list, ensure_ascii=False), hashed))


def count_active():
    row = fetchone("SELECT COUNT(*) AS c FROM api_keys WHERE active = 1")
    return row["c"] if row else 0


def log_api_request(client, method, path, status, ip, duration):
    try:
        execute(
            """INSERT INTO api_logs (time, client, method, path, status, ip, duration)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (now_ms(), client, method, path, int(status), ip, int(duration)),
        )
    except Exception as e:
        print(f"[APIKEY] log lỗi: {e}")


def list_api_logs(limit=100):
    rows = fetchall(
        "SELECT * FROM api_logs ORDER BY id DESC LIMIT ?", (limit,)
    )
    return [{
        "time": fmt_time(r["time"]),
        "client": r["client"],
        "method": r["method"],
        "path": r["path"],
        "status": r["status"],
        "ip": r["ip"],
        "duration": r["duration"],
    } for r in rows]


def cleanup_api_logs(keep=10000):
    try:
        execute(
            "DELETE FROM api_logs WHERE id NOT IN "
            "(SELECT id FROM api_logs ORDER BY id DESC LIMIT ?)",
            (keep,),
        )
    except Exception as e:
        print(f"[APIKEY] cleanup lỗi: {e}")
