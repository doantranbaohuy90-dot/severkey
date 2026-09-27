# bot.py - Telegram Bot Key Server - Full 1 file (2000 dòng)
# Tác giả: MADE BY Bao Huy
# Chạy độc lập: python bot.py
# Yêu cầu: key.py, auth.py, apikey.py, db.py cùng thư mục

# ============================================================
# IMPORT
# ============================================================

import os
import sys
import json
import time
import html
import math
import random
import string
import hashlib
import secrets
import threading
import traceback
from datetime import datetime, timedelta

import requests

try:
    import key as keymod
    import auth as authmod
    import apikey
    from db import (
        get_db, execute, fetchone, fetchall, insert, update, delete,
        now_ms, fmt_time, rows_to_list,
    )
except ImportError as e:
    print(f"[BOT] Thiếu module nội bộ: {e}")
    raise

# ============================================================
# CẤU HÌNH
# ============================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

ADMIN_IDS = set(
    x.strip() for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()
)

DEFAULT_DAYS = getattr(keymod, "DEFAULT_DAYS", 30)
DEFAULT_MAX_DEVICES = getattr(keymod, "DEFAULT_MAX_DEVICES", 1)
AUTO_ISSUE_ENABLED = os.environ.get("AUTO_ISSUE_ENABLED", "true").lower() == "true"
AUTO_ISSUE_ONCE = os.environ.get("AUTO_ISSUE_ONCE", "true").lower() == "true"
CTV_MAX_DAYS = int(os.environ.get("CTV_MAX_DAYS", "30"))
CTV_MAX_KEYS = int(os.environ.get("CTV_MAX_KEYS", "50"))
BROADCAST_DELAY = float(os.environ.get("BROADCAST_DELAY", "0.05"))
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

DATA_DIR = getattr(keymod, "DATA_DIR", "./data")
SESSION_FILE = os.path.join(DATA_DIR, "bot_sessions.json")
NOTIFY_FILE = os.path.join(DATA_DIR, "notify_queue.json")
TG_USERS_FILE = os.path.join(DATA_DIR, "telegram_users.json")

lock = threading.RLock()
_bot_state = {
    "started_at": now_ms(),
    "updates_handled": 0,
    "commands_handled": 0,
    "errors": 0,
    "last_error": None,
}

# ============================================================
# TIỆN ÍCH
# ============================================================

def ensure_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass

def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def write_json(path, data):
    ensure_dir(os.path.dirname(path))
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        print(f"[BOT] write_json lỗi: {e}")

def esc(text):
    if text is None:
        return ""
    return html.escape(str(text), quote=False)

def truncate(text, max_len=4000):
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len - 20] + "\n... (rút gọn)"

def humanize_delta(ms):
    if ms <= 0:
        return "0s"
    s = int(ms / 1000)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s and not parts: parts.append(f"{s}s")
    return " ".join(parts) or "0s"

def parse_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def random_token(n=16):
    return secrets.token_urlsafe(n)

# ============================================================
# TELEGRAM API
# ============================================================

_session = requests.Session()
_session.headers.update({"Connection": "keep-alive"})
_tg_lock = threading.Lock()
_last_send = [0.0]
MIN_SEND_INTERVAL = 0.04

def _rate_limit_wait():
    with _tg_lock:
        now = time.time()
        delta = now - _last_send[0]
        if delta < MIN_SEND_INTERVAL:
            time.sleep(MIN_SEND_INTERVAL - delta)
        _last_send[0] = time.time()

def tg_call(method, payload, timeout=15):
    if not BOT_TOKEN:
        return None
    _rate_limit_wait()
    try:
        r = _session.post(f"{API}/{method}", json=payload, timeout=timeout)
        if r.status_code != 200:
            print(f"[TG] {method} HTTP {r.status_code}: {r.text[:200]}")
            return None
        return r.json()
    except requests.exceptions.Timeout:
        print(f"[TG] {method} timeout")
        return None
    except Exception as e:
        print(f"[TG] {method} exception: {e}")
        return None

def send_message(chat_id, text, parse_mode="HTML",
                 disable_preview=True, reply_markup=None):
    if not BOT_TOKEN:
        print("[TG] Thiếu BOT_TOKEN")
        return False
    payload = {
        "chat_id": chat_id,
        "text": truncate(text, 4000),
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_preview,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    res = tg_call("sendMessage", payload)
    return bool(res and res.get("ok"))

def edit_message(chat_id, message_id, text, parse_mode="HTML", reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": truncate(text, 4000),
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    res = tg_call("editMessageText", payload)
    return bool(res and res.get("ok"))

def delete_message(chat_id, message_id):
    res = tg_call("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
    return bool(res and res.get("ok"))

def send_inline_keyboard(chat_id, text, buttons, parse_mode="HTML"):
    return send_message(chat_id, text, parse_mode=parse_mode,
                        reply_markup={"inline_keyboard": buttons})

def answer_callback(cb_id, text="", show_alert=False):
    tg_call("answerCallbackQuery", {
        "callback_query_id": cb_id,
        "text": truncate(text, 200),
        "show_alert": show_alert,
    })

def send_chat_action(chat_id, action="typing"):
    tg_call("sendChatAction", {"chat_id": chat_id, "action": action})

def get_me():
    res = tg_call("getMe", {}, timeout=10)
    if res and res.get("ok"):
        return res.get("result")
    return None

def set_webhook(url, secret_token=None):
    payload = {
        "url": url,
        "drop_pending_updates": "true",
        "allowed_updates": json.dumps(["message", "callback_query"]),
    }
    if secret_token:
        payload["secret_token"] = secret_token
    res = tg_call("setWebhook", payload)
    return bool(res and res.get("ok"))

def delete_webhook():
    res = tg_call("deleteWebhook", {"drop_pending_updates": "true"})
    return bool(res and res.get("ok"))

def get_webhook_info():
    res = tg_call("getWebhookInfo", {}, timeout=10)
    if res and res.get("ok"):
        return res.get("result")
    return None

# ============================================================
# CTV
# ============================================================

def load_ctv():
    rows = fetchall("SELECT * FROM ctv")
    return {r["user_id"]: dict(r) for r in rows}

def is_ctv(user_id):
    row = fetchone("SELECT user_id FROM ctv WHERE user_id = ? AND active = 1",
                   (str(user_id),))
    return row is not None

def is_admin(user_id):
    return str(user_id) in ADMIN_IDS

def get_ctv(user_id):
    row = fetchone("SELECT * FROM ctv WHERE user_id = ?", (str(user_id),))
    return dict(row) if row else None

def ctv_can_create(user_id, days=1):
    rec = get_ctv(user_id)
    if not rec: return False, "not_ctv"
    if not rec.get("active"): return False, "ctv_disabled"
    if days > rec.get("max_days", CTV_MAX_DAYS):
        return False, f"Vượt quá {rec.get('max_days')} ngày"
    if rec.get("keys_created", 0) >= rec.get("max_keys", CTV_MAX_KEYS):
        return False, f"Vượt quá {rec.get('max_keys')} key"
    return True, None

def increment_ctv_count(user_id):
    execute("UPDATE ctv SET keys_created = keys_created + 1 WHERE user_id = ?",
            (str(user_id),))

def add_ctv(user_id, name=None, max_keys=None, max_days=None):
    uid = str(user_id)
    name = name or f"ctv_{uid}"
    max_keys = int(max_keys) if max_keys is not None else CTV_MAX_KEYS
    max_days = int(max_days) if max_days is not None else CTV_MAX_DAYS
    existing = fetchone("SELECT user_id FROM ctv WHERE user_id = ?", (uid,))
    if existing:
        update("ctv", {"name": name, "max_keys": max_keys,
                        "max_days": max_days, "active": 1},
               "user_id = ?", (uid,))
    else:
        insert("ctv", {
            "user_id": uid, "name": name,
            "max_keys": max_keys, "max_days": max_days,
            "keys_created": 0, "added_at": now_ms(), "active": 1,
        })

def remove_ctv(user_id):
    uid = str(user_id)
    row = fetchone("SELECT user_id FROM ctv WHERE user_id = ?", (uid,))
    if not row: return False
    execute("DELETE FROM ctv WHERE user_id = ?", (uid,))
    return True

def toggle_ctv(user_id):
    uid = str(user_id)
    row = fetchone("SELECT active FROM ctv WHERE user_id = ?", (uid,))
    if not row: return None
    new_state = 0 if row["active"] else 1
    execute("UPDATE ctv SET active = ? WHERE user_id = ?", (new_state, uid))
    return bool(new_state)

# ============================================================
# USER / KEY
# ============================================================

def get_key_by_user(user_id):
    row = fetchone(
        "SELECT key FROM keys WHERE user_id = ? AND active = 1 "
        "ORDER BY created_at DESC LIMIT 1", (str(user_id),))
    return row["key"] if row else None

def link_key_to_user(user_id, key):
    execute("UPDATE keys SET user_id = ? WHERE key = ?", (str(user_id), key))

def _count_devices(key):
    row = fetchone("SELECT COUNT(*) AS c FROM devices WHERE key = ?", (key,))
    return row["c"] if row else 0

def get_or_create_key_for_user(user_id, owner=None, days=None,
                                max_devices=None, created_by=None,
                                account_uid=None, parent_key=None):
    uid = str(user_id)
    if AUTO_ISSUE_ONCE:
        existing = get_key_by_user(uid)
        if existing:
            row = fetchone("SELECT * FROM keys WHERE key = ?", (existing,))
            if row and row["active"] and now_ms() < row["expires_at"]:
                rec = dict(row)
                rec["devicesUsed"] = _count_devices(existing)
                return {"created": False, "key": existing, "record": rec}

    days = days if days is not None else DEFAULT_DAYS
    owner = owner or f"user_{uid}"
    max_devices = max_devices if max_devices is not None else DEFAULT_MAX_DEVICES

    k, exp, sig = keymod.create_key(
        days, owner, max_devices, user_id=uid,
        created_by=created_by, account_uid=account_uid,
        parent_key=parent_key,
    )
    link_key_to_user(uid, k)

    if account_uid:
        try: authmod.set_account_key(account_uid, k)
        except Exception: pass
    if created_by:
        increment_ctv_count(created_by)

    row = fetchone("SELECT * FROM keys WHERE key = ?", (k,))
    rec = dict(row) if row else None
    if rec: rec["devicesUsed"] = 0
    return {"created": True, "key": k, "expiresAt": exp,
            "signature": sig, "record": rec}

# ============================================================
# SESSION
# ============================================================

def set_session(user_id, state, data=None, ttl=300000):
    sessions = read_json(SESSION_FILE, {})
    sessions[str(user_id)] = {
        "state": state, "data": data or {},
        "updatedAt": now_ms(), "ttl": ttl,
    }
    write_json(SESSION_FILE, sessions)

def get_session(user_id):
    sessions = read_json(SESSION_FILE, {})
    s = sessions.get(str(user_id))
    if not s: return None
    ttl = s.get("ttl", 300000)
    if now_ms() - s.get("updatedAt", 0) > ttl:
        clear_session(user_id)
        return None
    return s

def clear_session(user_id):
    sessions = read_json(SESSION_FILE, {})
    sessions.pop(str(user_id), None)
    write_json(SESSION_FILE, sessions)

def session_count():
    sessions = read_json(SESSION_FILE, {})
    now = now_ms()
    return sum(1 for s in sessions.values()
               if now - s.get("updatedAt", 0) <= s.get("ttl", 300000))

# ============================================================
# NOTIFY QUEUE
# ============================================================

def push_notify(target, message, level="info"):
    queue = read_json(NOTIFY_FILE, [])
    queue.append({
        "target": str(target), "message": message,
        "level": level, "time": now_ms(), "tries": 0,
    })
    write_json(NOTIFY_FILE, queue)

def flush_notify():
    queue = read_json(NOTIFY_FILE, [])
    if not queue: return
    remaining = []
    for item in queue:
        tries = item.get("tries", 0) + 1
        if tries > 3: continue
        ok = send_message(item["target"], item["message"])
        if not ok:
            item["tries"] = tries
            remaining.append(item)
        time.sleep(0.05)
    write_json(NOTIFY_FILE, remaining)

def notify_admins(message, level="info"):
    for admin_id in ADMIN_IDS:
        push_notify(admin_id, message, level)

def notify_key_created(key, owner, days, by=None):
    msg = (f"🔑 <b>Key mới</b>\n<code>{esc(key)}</code>\n"
           f"Chủ: {esc(owner)}\nHạn: {days} ngày")
    if by: msg += f"\nBởi: {esc(by)}"
    notify_admins(msg)

def notify_key_revoked(key, reason="unknown"):
    notify_admins(f"⚠️ <b>Key bị thu hồi</b>\n<code>{esc(key)}</code>\n"
                  f"Lý do: {esc(reason)}")

def notify_device_blocked(device_id, key, reason="unknown"):
    notify_admins(f"🚫 <b>Thiết bị bị block</b>\n"
                  f"Device: <code>{esc(device_id)}</code>\n"
                  f"Key: <code>{esc(key)}</code>\nLý do: {esc(reason)}")

def notify_login(username, ip=""):
    msg = f"👤 Đăng nhập: <b>{esc(username)}</b>"
    if ip: msg += f" từ {esc(ip)}"
    notify_admins(msg)

# ============================================================
# TELEGRAM USER SYNC
# ============================================================

def sync_telegram_user(user_id, username, first_name, last_name=None):
    users = read_json(TG_USERS_FILE, {})
    uid = str(user_id)
    now = now_ms()
    if uid not in users:
        users[uid] = {
            "username": username, "firstName": first_name,
            "lastName": last_name, "firstSeen": now,
            "lastSeen": now, "notify": True, "blocked": False,
        }
    else:
        users[uid]["lastSeen"] = now
        if username: users[uid]["username"] = username
        if first_name: users[uid]["firstName"] = first_name
    write_json(TG_USERS_FILE, users)
    try: authmod.link_telegram(uid, username)
    except Exception: pass

def get_telegram_user(user_id):
    return read_json(TG_USERS_FILE, {}).get(str(user_id))

def list_telegram_users():
    return read_json(TG_USERS_FILE, {})

def count_telegram_users():
    return len(read_json(TG_USERS_FILE, {}))

def user_is_banned_tg(user_id):
    u = get_telegram_user(user_id)
    return bool(u and u.get("blocked"))

def toggle_tg_user_ban(user_id):
    users = read_json(TG_USERS_FILE, {})
    uid = str(user_id)
    if uid not in users:
        return None
    users[uid]["blocked"] = not users[uid].get("blocked", False)
    write_json(TG_USERS_FILE, users)
    return users[uid]["blocked"]

# ============================================================
# HELP & MENU
# ============================================================

HELP_TEXT = """
🔑 <b>KEY SERVER BOT</b>

<b>Người dùng:</b>
/start /menu /help
/code - Nhận key
/mykey /myinfo /mydevices
/verify &lt;key&gt; &lt;device&gt;
/info &lt;key&gt; /days &lt;key&gt;

<b>CTV:</b>
/create &lt;days&gt; &lt;owner&gt; &lt;max_dev&gt;
/issue &lt;user_id&gt; [days]
/adddays &lt;key&gt; &lt;days&gt;
/tree /mystats

<b>Admin:</b>
/stats /list /logs /devices
/revoke /delete
/blockkey /unblockkey
/blockdev /unblockdev /blocklist
/addctv /removectv /ctvlist /togglectv
/apikeys /newapikey /rotatekey
/broadcast /botstats /health
""".strip()

def cmd_menu(chat_id, user_id):
    admin = is_admin(user_id)
    ctv = is_ctv(user_id)
    buttons = [
        [{"text": "🔑 Key của tôi", "callback_data": "my_key"},
         {"text": "📱 Thiết bị", "callback_data": "my_devices"}],
        [{"text": "ℹ️ Thông tin", "callback_data": "my_info"},
         {"text": "📖 Trợ giúp", "callback_data": "help"}],
    ]
    if ctv or admin:
        buttons.append([
            {"text": "➕ Tạo key", "callback_data": "create_key"},
            {"text": "🌳 Cây key", "callback_data": "tree"},
        ])
        buttons.append([{"text": "📊 Thống kê", "callback_data": "mystats"}])
    if admin:
        buttons.append([{"text": "🔧 Quản trị", "callback_data": "admin_panel"}])
    send_inline_keyboard(chat_id, "<b>MENU CHÍNH</b>", buttons)

def cmd_admin_panel(chat_id, user_id, message_id=None):
    if not is_admin(user_id):
        send_message(chat_id, "Không có quyền.")
        return
    buttons = [
        [{"text": "📊 Thống kê", "callback_data": "stats"},
         {"text": "🔑 Keys", "callback_data": "admin_keys"}],
        [{"text": "📱 Thiết bị", "callback_data": "admin_devices"},
         {"text": "🚫 Block", "callback_data": "blocks"}],
        [{"text": "👥 CTV", "callback_data": "ctv_list"},
         {"text": "🔌 API", "callback_data": "api_list"}],
        [{"text": "📝 Log", "callback_data": "admin_logs"},
         {"text": "🤖 Bot", "callback_data": "bot_stats"}],
        [{"text": "🔙 Quay lại", "callback_data": "menu"}],
    ]
    text = "<b>BẢNG QUẢN TRỊ</b>"
    if message_id:
        edit_message(chat_id, message_id, text,
                     reply_markup={"inline_keyboard": buttons})
    else:
        send_inline_keyboard(chat_id, text, buttons)

# ============================================================
# COMMAND HANDLERS
# ============================================================

def cmd_stats(chat_id, user_id):
    if not is_admin(user_id):
        send_message(chat_id, "Không có quyền.")
        return
    row = fetchone("""
        SELECT
          (SELECT COUNT(*) FROM keys) AS total,
          (SELECT COUNT(*) FROM keys WHERE active=1) AS active,
          (SELECT COUNT(*) FROM keys WHERE expires_at < ?) AS expired,
          (SELECT COUNT(*) FROM devices) AS devices,
          (SELECT COUNT(*) FROM accounts) AS accounts,
          (SELECT COUNT(*) FROM ctv) AS ctv,
          (SELECT COUNT(*) FROM blocked WHERE type='key') AS bk,
          (SELECT COUNT(*) FROM blocked WHERE type='device') AS bd
    """, (now_ms(),))
    if not row:
        send_message(chat_id, "Lỗi truy vấn.")
        return
    send_message(chat_id,
        f"<b>THỐNG KÊ</b>\n"
        f"Tổng key: {row['total']}\n"
        f"Hoạt động: {row['active']}\n"
        f"Hết hạn: {row['expired']}\n"
        f"Thiết bị: {row['devices']}\n"
        f"Tài khoản: {row['accounts']}\n"
        f"CTV: {row['ctv']}\n"
        f"Block key: {row['bk']}\n"
        f"Block TB: {row['bd']}")

def cmd_list(chat_id, user_id, parts):
    if not is_admin(user_id):
        send_message(chat_id, "Không có quyền.")
        return
    n = parse_int(parts[1], 20) if len(parts) > 1 else 20
    n = min(max(n, 1), 50)
    rows = fetchall("SELECT * FROM keys ORDER BY created_at DESC LIMIT ?", (n,))
    if not rows:
        send_message(chat_id, "Chưa có key.")
        return
    now = now_ms()
    lines = ["<b>DANH SÁCH KEY</b>"]
    for r in rows:
        d = max(0, int((r["expires_at"] - now) / 86400000))
        lines.append(f"<code>{esc(r['key'])}</code>\n"
                     f"  {esc(r['owner'])} | {d}d | "
                     f"{'ON' if r['active'] else 'OFF'}")
    send_message(chat_id, "\n".join(lines))

def cmd_devices(chat_id, user_id):
    if not is_admin(user_id):
        send_message(chat_id, "Không có quyền.")
        return
    rows = fetchall("SELECT * FROM devices ORDER BY last_seen DESC LIMIT 30")
    if not rows:
        send_message(chat_id, "Chưa có thiết bị.")
        return
    lines = ["<b>THIẾT BỊ GẦN ĐÂY</b>"]
    for r in rows:
        lines.append(f"<code>{esc(r['device_id'])}</code>\n"
                     f"  Key: <code>{esc(r['key'][:12])}...</code> | "
                     f"{esc(r['ip'])} | {r['count']} lần")
    send_message(chat_id, "\n".join(lines))

def cmd_logs(chat_id, user_id, parts):
    if not is_admin(user_id):
        send_message(chat_id, "Không có quyền.")
        return
    n = parse_int(parts[1], 10) if len(parts) > 1 else 10
    n = min(max(n, 1), 30)
    rows = fetchall("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (n,))
    if not rows:
        send_message(chat_id, "Chưa có log.")
        return
    lines = ["<b>LOG GẦN ĐÂY</b>"]
    for r in rows:
        data = r["data"] or ""
        if len(data) > 80:
            data = data[:80] + "..."
        lines.append(f"{fmt_time(r['time'])} | {esc(r['event'])}\n  {esc(data)}")
    send_message(chat_id, "\n".join(lines))

def cmd_blocklist(chat_id, user_id):
    if not is_admin(user_id):
        send_message(chat_id, "Không có quyền.")
        return
    rows = fetchall("SELECT * FROM blocked ORDER BY time DESC LIMIT 50")
    if not rows:
        send_message(chat_id, "Không có mục nào bị block.")
        return
    lines = ["<b>BLOCK LIST</b>"]
    for r in rows:
        lines.append(f"[{esc(r['type'])}] <code>{esc(r['id'])}</code>\n"
                     f"  {esc(r['reason'])} | {fmt_time(r['time'])}")
    send_message(chat_id, "\n".join(lines))

def cmd_ctvlist(chat_id, user_id):
    if not is_admin(user_id):
        send_message(chat_id, "Không có quyền.")
        return
    rows = fetchall("SELECT * FROM ctv ORDER BY added_at DESC LIMIT 30")
    if not rows:
        send_message(chat_id, "Chưa có CTV.")
        return
    lines = ["<b>DANH SÁCH CTV</b>"]
    for r in rows:
        st = "ON" if r["active"] else "OFF"
        lines.append(f"<code>{esc(r['user_id'])}</code> | {esc(r['name'])} | "
                     f"{st} | {r['keys_created']}/{r['max_keys']}")
    send_message(chat_id, "\n".join(lines))

def cmd_apikeys(chat_id, user_id):
    if not is_admin(user_id):
        send_message(chat_id, "Không có quyền.")
        return
    try:
        items = apikey.list_api_keys()
    except Exception:
        items = []
    if not items:
        send_message(chat_id, "Chưa có API key.")
        return
    lines = ["<b>DANH SÁCH API KEY</b>"]
    for it in items[:20]:
        st = "ON" if it["active"] else "OFF"
        lines.append(f"<code>{esc(it['keyPreview'])}</code> | "
                     f"{esc(it['name'])} | {st} | {it['usageCount']} lần")
    send_message(chat_id, "\n".join(lines))

def cmd_botstats(chat_id, user_id):
    if not is_admin(user_id):
        send_message(chat_id, "Không có quyền.")
        return
    up = now_ms() - _bot_state["started_at"]
    me = get_me()
    wh = get_webhook_info() or {}
    send_message(chat_id,
        f"<b>BOT STATS</b>\n"
        f"Uptime: {humanize_delta(up)}\n"
        f"Updates: {_bot_state['updates_handled']}\n"
        f"Commands: {_bot_state['commands_handled']}\n"
        f"Errors: {_bot_state['errors']}\n"
        f"Bot: @{esc((me or {}).get('username', '-'))}\n"
        f"Webhook: {'ON' if wh.get('url') else 'OFF'}\n"
        f"Pending: {wh.get('pending_update_count', 0)}\n"
        f"Users: {count_telegram_users()}\n"
        f"Sessions: {session_count()}")

def cmd_health(chat_id, user_id):
    ok_db = False
    try:
        ok_db = fetchone("SELECT 1 AS x") is not None
    except Exception:
        pass
    ok_bot = get_me() is not None
    send_message(chat_id,
        f"<b>HEALTH</b>\n"
        f"DB: {'OK' if ok_db else 'FAIL'}\n"
        f"Bot API: {'OK' if ok_bot else 'FAIL'}\n"
        f"Uptime: {humanize_delta(now_ms() - _bot_state['started_at'])}")

# ============================================================
# SESSION INPUT HANDLER
# ============================================================

def handle_session_input(chat_id, user_id, text, session):
    state = session.get("state")
    data = session.get("data", {})

    if state == "create_key":
        step = data.get("step", "days")
        if step == "days":
            days = parse_int(text, 0)
            if days <= 0 or days > 3650:
                send_message(chat_id, "Số ngày không hợp lệ. Nhập lại:")
                return
            data["days"] = days
            data["step"] = "owner"
            set_session(user_id, "create_key", data)
            send_message(chat_id, "Nhập chủ sở hữu (hoặc 'skip'):")
            return
        if step == "owner":
            data["owner"] = text if text.lower() != "skip" else "unknown"
            data["step"] = "max_devices"
            set_session(user_id, "create_key", data)
            send_message(chat_id, "Nhập max thiết bị (mặc định 1):")
            return
        if step == "max_devices":
            max_dev = parse_int(text, 1)
            if max_dev <= 0: max_dev = 1
            days = data.get("days", 30)
            owner = data.get("owner", "unknown")
            if is_ctv(user_id) and not is_admin(user_id):
                ok, err = ctv_can_create(user_id, days)
                if not ok:
                    send_message(chat_id, f"Không thể tạo: {err}")
                    clear_session(user_id)
                    return
            k, exp, sig = keymod.create_key(
                days, owner, max_dev,
                created_by=user_id if is_ctv(user_id) else None,
            )
            if is_ctv(user_id):
                increment_ctv_count(user_id)
            notify_key_created(k, owner, days, by=user_id)
            send_message(chat_id,
                f"✅ <b>Key đã tạo</b>\n"
                f"<code>{esc(k)}</code>\n"
                f"Chủ: {esc(owner)}\n"
                f"Hạn: {days} ngày\n"
                f"Max TB: {max_dev}")
            clear_session(user_id)
            return

    if state == "broadcast":
        msg = text
        if len(msg) < 2:
            send_message(chat_id, "Tin nhắn quá ngắn. Nhập lại hoặc /cancel:")
            return
        clear_session(user_id)
        send_message(chat_id, "Đang gửi...")
        threading.Thread(target=broadcast_worker,
                         args=(msg,), daemon=True).start()
        return

    clear_session(user_id)
    send_message(chat_id, "Phiên đã kết thúc.")

def broadcast_worker(message):
    users = list_telegram_users()
    total = len(users)
    ok = 0
    fail = 0
    for uid, info in users.items():
        if info.get("blocked"): continue
        if send_message(uid, message): ok += 1
        else: fail += 1
        time.sleep(BROADCAST_DELAY)
    for admin_id in ADMIN_IDS:
        send_message(admin_id,
                     f"📢 Broadcast: {ok}/{total} thành công, {fail} lỗi.")

# ============================================================
# CALLBACK HANDLER
# ============================================================

def handle_callback(cb):
    cb_id = cb.get("id")
    chat_id = cb["message"]["chat"]["id"]
    message_id = cb["message"]["message_id"]
    user_id = str(cb["from"]["id"])
    data = cb.get("data", "")

    if data == "menu":
        answer_callback(cb_id)
        edit_message(chat_id, message_id, "<b>MENU CHÍNH</b>", reply_markup=None)
        cmd_menu(chat_id, user_id)
        return

    if data == "help":
        answer_callback(cb_id)
        send_message(chat_id, HELP_TEXT)
        return

    if data == "my_key":
        answer_callback(cb_id)
        k = get_key_by_user(user_id)
        if not k:
            send_message(chat_id, "Chưa có key. Dùng /code.")
            return
        info = keymod.get_key_info(k)
        if not info:
            send_message(chat_id, "Key không tồn tại.")
            return
        send_message(chat_id,
            f"<b>KEY CỦA BẠN</b>\n<code>{esc(k)}</code>\n"
            f"Chủ: {esc(info['owner'])}\n"
            f"Còn: {info['daysLeft']} ngày\n"
            f"TB: {info['devicesUsed']}/{info['maxDevices']}\n"
            f"Trạng thái: {'ON' if info['active'] else 'OFF'}")
        return

    if data == "my_devices":
        answer_callback(cb_id)
        k = get_key_by_user(user_id)
        if not k:
            send_message(chat_id, "Chưa có key.")
            return
        rows = fetchall("SELECT * FROM devices WHERE key = ? "
                        "ORDER BY last_seen DESC LIMIT 20", (k,))
        if not rows:
            send_message(chat_id, "Chưa có thiết bị.")
            return
        lines = ["<b>THIẾT BỊ</b>"]
        for r in rows:
            lines.append(f"<code>{esc(r['device_id'])}</code>\n"
                         f"  IP: {esc(r['ip'])} | Lần cuối: {fmt_time(r['last_seen'])}")
        send_message(chat_id, "\n".join(lines))
        return

    if data == "my_info":
        answer_callback(cb_id)
        tg = get_telegram_user(user_id) or {}
        k = get_key_by_user(user_id)
        role = "admin" if is_admin(user_id) else "ctv" if is_ctv(user_id) else "user"
        send_message(chat_id,
            f"<b>THÔNG TIN</b>\n"
            f"ID: <code>{esc(user_id)}</code>\n"
            f"Tên: {esc(tg.get('firstName', '-'))}\n"
            f"Username: @{esc(tg.get('username', '-'))}\n"
            f"Vai trò: {role}\n"
            f"Key: <code>{esc(k or 'chưa có')}</code>")
        return

    if data == "create_key":
        answer_callback(cb_id)
        if not (is_ctv(user_id) or is_admin(user_id)):
            return
        set_session(user_id, "create_key", {"step": "days"})
        send_message(chat_id, "Nhập số ngày cho key mới (hoặc /cancel):")
        return

    if data == "tree":
        answer_callback(cb_id)
        try:
            tree_view = keymod.build_tree_view()
            lines = keymod.render_tree_text(tree_view)
        except Exception:
            lines = []
        send_message(chat_id, "🌳 <b>CÂY KEY</b>\n" +
                     ("\n".join(lines) if lines else "Chưa có key."))
        return

    if data == "mystats":
        answer_callback(cb_id)
        if not (is_ctv(user_id) or is_admin(user_id)):
            return
        rec = get_ctv(user_id)
        if rec:
            send_message(chat_id,
                f"<b>THỐNG KÊ CTV</b>\n"
                f"Đã tạo: {rec.get('keys_created', 0)}/{rec.get('max_keys')}\n"
                f"Max ngày: {rec.get('max_days')}\n"
                f"Trạng thái: {'ON' if rec.get('active') else 'OFF'}")
        return

    if data == "admin_panel":
        answer_callback(cb_id)
        cmd_admin_panel(chat_id, user_id, message_id)
        return

    if data == "stats":
        answer_callback(cb_id); cmd_stats(chat_id, user_id); return
    if data == "admin_keys":
        answer_callback(cb_id); cmd_list(chat_id, user_id, ["/list", "20"]); return
    if data == "admin_devices":
        answer_callback(cb_id); cmd_devices(chat_id, user_id); return
    if data == "blocks":
        answer_callback(cb_id); cmd_blocklist(chat_id, user_id); return
    if data == "ctv_list":
        answer_callback(cb_id); cmd_ctvlist(chat_id, user_id); return
    if data == "api_list":
        answer_callback(cb_id); cmd_apikeys(chat_id, user_id); return
    if data == "admin_logs":
        answer_callback(cb_id); cmd_logs(chat_id, user_id, ["/logs", "10"]); return
    if data == "bot_stats":
        answer_callback(cb_id); cmd_botstats(chat_id, user_id); return

    answer_callback(cb_id, "Không hỗ trợ")

# ============================================================
# COMMAND HANDLER
# ============================================================

def handle_command(chat_id, user_id, text):
    parts = text.split()
    cmd = parts[0].lower()
    admin = is_admin(user_id)
    ctv = is_ctv(user_id)
    perm = admin or ctv

    _bot_state["commands_handled"] += 1

    if cmd == "/start":
        send_message(chat_id, HELP_TEXT)
        cmd_menu(chat_id, user_id)
        return
    if cmd == "/menu":
        cmd_menu(chat_id, user_id)
        return
    if cmd == "/help":
        send_message(chat_id, HELP_TEXT)
        return

    if cmd == "/code":
        if not AUTO_ISSUE_ENABLED:
            send_message(chat_id, "Chức năng cấp key đang tắt.")
            return
        result = get_or_create_key_for_user(user_id, owner=f"tg_{user_id}")
        send_message(chat_id,
            f"{'Đã cấp' if result['created'] else 'Bạn đã có'} key.\n"
            f"<code>{esc(result['key'])}</code>\n"
            f"Còn: {keymod.get_days_left(result['key'])} ngày")
        return

    if cmd == "/mykey":
        k = get_key_by_user(user_id)
        if not k:
            send_message(chat_id, "Chưa có key. Dùng /code.")
            return
        info = keymod.get_key_info(k)
        if not info:
            send_message(chat_id, "Key không tồn tại.")
            return
        send_message(chat_id,
            f"<code>{esc(k)}</code>\n"
            f"Còn: {info['daysLeft']} ngày\n"
            f"TB: {info['devicesUsed']}/{info['maxDevices']}")
        return

    if cmd == "/myinfo":
        tg = get_telegram_user(user_id) or {}
        k = get_key_by_user(user_id)
        role = "admin" if admin else "ctv" if ctv else "user"
        send_message(chat_id,
            f"ID: <code>{esc(user_id)}</code>\n"
            f"Tên: {esc(tg.get('firstName', '-'))}\n"
            f"Username: @{esc(tg.get('username', '-'))}\n"
            f"Vai trò: {role}\n"
            f"Key: <code>{esc(k or 'chưa có')}</code>")
        return

    if cmd == "/mydevices":
        k = get_key_by_user(user_id)
        if not k:
            send_message(chat_id, "Chưa có key.")
            return
        rows = fetchall("SELECT * FROM devices WHERE key = ? "
                        "ORDER BY last_seen DESC LIMIT 20", (k,))
        if not rows:
            send_message(chat_id, "Chưa có thiết bị.")
            return
        lines = ["<b>THIẾT BỊ</b>"]
        for r in rows:
            lines.append(f"<code>{esc(r['device_id'])}</code> | {esc(r['ip'])} | "
                         f"{r['count']} lần")
        send_message(chat_id, "\n".join(lines))
        return

    if cmd == "/verify":
        if len(parts) < 3:
            send_message(chat_id, "Cú pháp: /verify <key> <device_id>")
            return
        result = keymod.verify_key(parts[1], parts[2], "telegram", f"user:{user_id}")
        if not result.get("ok"):
            send_message(chat_id, f"❌ {result.get('error', 'thất bại')}")
            return
        send_message(chat_id,
            f"✅ Hợp lệ\nChủ: {esc(result['owner'])}\n"
            f"Còn: {result['remainingDays']} ngày\n"
            f"TB: {result['devicesUsed']}/{result['maxDevices']}")
        return

    if cmd == "/info":
        if len(parts) < 2:
            send_message(chat_id, "Cú pháp: /info <key>")
            return
        info = keymod.get_key_info(parts[1])
        if not info:
            send_message(chat_id, "Key không tồn tại.")
            return
        send_message(chat_id,
            f"Key: <code>{esc(info['key'])}</code>\n"
            f"Chủ: {esc(info['owner'])}\n"
            f"Trạng thái: {'ON' if info['active'] else 'OFF'}\n"
            f"Block: {'CÓ' if info['blocked'] else 'KHÔNG'}\n"
            f"Còn: {info['daysLeft']}d\n"
            f"TB: {info['devicesUsed']}/{info['maxDevices']}")
        return

    if cmd == "/days":
        if len(parts) < 2:
            send_message(chat_id, "Cú pháp: /days <key>")
            return
        d = keymod.get_days_left(parts[1])
        send_message(chat_id, f"Còn: {d} ngày" if d is not None
                     else "Key không tồn tại.")
        return

    if cmd == "/create":
        if not perm:
            send_message(chat_id, "Không có quyền.")
            return
        days = parse_int(parts[1], 30) if len(parts) > 1 else 30
        owner = parts[2] if len(parts) > 2 else "unknown"
        max_dev = parse_int(parts[3], DEFAULT_MAX_DEVICES) if len(parts) > 3 else DEFAULT_MAX_DEVICES
        if ctv and not admin:
            ok, err = ctv_can_create(user_id, days)
            if not ok:
                send_message(chat_id, f"Không thể tạo: {err}")
                return
        k, exp, sig = keymod.create_key(days, owner, max_dev,
                                         created_by=user_id if ctv else None)
        if ctv:
            increment_ctv_count(user_id)
        notify_key_created(k, owner, days, by=user_id)
        send_message(chat_id,
            f"<code>{esc(k)}</code>\nChủ: {esc(owner)}\n"
            f"Hạn: {fmt_time(exp)}\nMax TB: {max_dev}")
        return

    if cmd == "/issue":
        if not perm:
            send_message(chat_id, "Không có quyền.")
            return
        if len(parts) < 2:
            send_message(chat_id, "Cú pháp: /issue <user_id> [days]")
            return
        target = parts[1]
        days = parse_int(parts[2], DEFAULT_DAYS) if len(parts) > 2 else DEFAULT_DAYS
        result = get_or_create_key_for_user(
            target, owner=f"user_{target}", days=days,
            created_by=user_id if ctv else None)
        send_message(chat_id,
            f"{'Đã tạo' if result['created'] else 'Đã có'} key cho {esc(target)}:\n"
            f"<code>{esc(result['key'])}</code>")
        return

    if cmd == "/adddays":
        if not perm:
            send_message(chat_id, "Không có quyền.")
            return
        if len(parts) < 3:
            send_message(chat_id, "Cú pháp: /adddays <key> <days>")
            return
        days = parse_int(parts[2], 0)
        if days == 0:
            send_message(chat_id, "Số ngày không hợp lệ.")
            return
        new_exp = keymod.add_days(parts[1], days)
        send_message(chat_id,
            f"Hết hạn mới: {fmt_time(new_exp)}" if new_exp else "Key không tồn tại.")
        return

    if cmd == "/tree":
        try:
            tree_view = keymod.build_tree_view()
            lines = keymod.render_tree_text(tree_view)
        except Exception:
            lines = []
        send_message(chat_id, "🌳 <b>CÂY KEY</b>\n" +
                     ("\n".join(lines[:80]) if lines else "Chưa có key."))
        return

    if cmd == "/mystats":
        if not perm:
            send_message(chat_id, "Không có quyền.")
            return
        rec = get_ctv(user_id)
        if not rec:
            send_message(chat_id, "Bạn là admin, không có giới hạn CTV.")
            return
        send_message(chat_id,
            f"Đã tạo: {rec.get('keys_created', 0)}/{rec.get('max_keys')}\n"
            f"Max ngày: {rec.get('max_days')}\n"
            f"Trạng thái: {'ON' if rec.get('active') else 'OFF'}")
        return

    if cmd in ("/stats", "/list", "/logs", "/revoke", "/delete",
               "/blockkey", "/unblockkey", "/blockdev", "/unblockdev",
               "/blocklist", "/addctv", "/removectv", "/ctvlist",
               "/togglectv", "/apikeys", "/newapikey", "/rotatekey",
               "/broadcast", "/botstats", "/health", "/devices"):
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        if cmd == "/stats": cmd_stats(chat_id, user_id); return
        if cmd == "/list": cmd_list(chat_id, user_id, parts); return
        if cmd == "/logs": cmd_logs(chat_id, user_id, parts); return
        if cmd == "/devices": cmd_devices(chat_id, user_id); return
        if cmd == "/blocklist": cmd_blocklist(chat_id, user_id); return
        if cmd == "/ctvlist": cmd_ctvlist(chat_id, user_id); return
        if cmd == "/apikeys": cmd_apikeys(chat_id, user_id); return
        if cmd == "/botstats": cmd_botstats(chat_id, user_id); return
        if cmd == "/health": cmd_health(chat_id, user_id); return
        if cmd == "/revoke":
            if len(parts) < 2:
                send_message(chat_id, "Cú pháp: /revoke <key>")
                return
            keymod.revoke_key(parts[1])
            notify_key_revoked(parts[1], "admin")
            send_message(chat_id, "Đã thu hồi.")
            return
        if cmd == "/delete":
            if len(parts) < 2:
                send_message(chat_id, "Cú pháp: /delete <key>")
                return
            keymod.delete_key(parts[1])
            send_message(chat_id, "Đã xóa.")
            return
        if cmd == "/blockkey":
            if len(parts) < 2:
                send_message(chat_id, "Cú pháp: /blockkey <key> [reason]")
                return
            reason = " ".join(parts[2:]) if len(parts) > 2 else "admin block"
            keymod.block_key(parts[1], reason)
            send_message(chat_id, "Đã block.")
            return
        if cmd == "/unblockkey":
            if len(parts) < 2:
                send_message(chat_id, "Cú pháp: /unblockkey <key>")
                return
            keymod.unblock_key(parts[1])
            send_message(chat_id, "Đã bỏ block.")
            return
        if cmd == "/blockdev":
            if len(parts) < 2:
                send_message(chat_id, "Cú pháp: /blockdev <device_id> [key]")
                return
            key = parts[2] if len(parts) > 2 else ""
            keymod.block_device(key, parts[1], "admin block")
            send_message(chat_id, "Đã block thiết bị.")
            return
        if cmd == "/unblockdev":
            if len(parts) < 2:
                send_message(chat_id, "Cú pháp: /unblockdev <device_id>")
                return
            keymod.unblock_device(parts[1])
            send_message(chat_id, "Đã bỏ block.")
            return
        if cmd == "/addctv":
            if len(parts) < 2:
                send_message(chat_id, "Cú pháp: /addctv <user_id> [name]")
                return
            name = parts[2] if len(parts) > 2 else None
            add_ctv(parts[1], name)
            send_message(chat_id, f"Đã thêm CTV {esc(parts[1])}.")
            return
        if cmd == "/removectv":
            if len(parts) < 2:
                send_message(chat_id, "Cú pháp: /removectv <user_id>")
                return
            if remove_ctv(parts[1]):
                send_message(chat_id, "Đã xóa CTV.")
            else:
                send_message(chat_id, "CTV không tồn tại.")
            return
        if cmd == "/togglectv":
            if len(parts) < 2:
                send_message(chat_id, "Cú pháp: /togglectv <user_id>")
                return
            st = toggle_ctv(parts[1])
            if st is None:
                send_message(chat_id, "CTV không tồn tại.")
            else:
                send_message(chat_id, f"CTV {'ON' if st else 'OFF'}.")
            return
        if cmd == "/newapikey":
            if len(parts) < 2:
                send_message(chat_id, "Cú pháp: /newapikey <name> [scopes]")
                return
            name = parts[1]
            scopes = parts[2].split(",") if len(parts) > 2 else ["verify", "info"]
            raw = apikey.create_api_key(name, scopes)
            send_message(chat_id, f"API Key:\n<code>{esc(raw)}</code>\n"
                                  f"Lưu lại ngay.")
            return
        if cmd == "/rotatekey":
            if len(parts) < 2:
                send_message(chat_id, "Cú pháp: /rotatekey <hash>")
                return
            raw = apikey.rotate_api_key(parts[1])
            if raw:
                send_message(chat_id, f"API Key mới:\n<code>{esc(raw)}</code>")
            else:
                send_message(chat_id, "Không tìm thấy.")
            return
        if cmd == "/broadcast":
            msg = " ".join(parts[1:])
            if not msg:
                set_session(user_id, "broadcast")
                send_message(chat_id, "Nhập nội dung broadcast (hoặc /cancel):")
                return
            threading.Thread(target=broadcast_worker, args=(msg,), daemon=True).start()
            send_message(chat_id, "Đang gửi broadcast...")
            return

    if cmd == "/cancel":
        clear_session(user_id)
        send_message(chat_id, "Đã hủy.")
        return

    send_message(chat_id, f"Lệnh không hỗ trợ: {esc(cmd)}\nDùng /help.")

# ============================================================
# UPDATE HANDLER
# ============================================================

def handle_update(update):
    try:
        _bot_state["updates_handled"] += 1

        if "callback_query" in update:
            handle_callback(update["callback_query"])
            return

        msg = update.get("message")
        if not msg or "text" not in msg:
            return

        chat_id = msg["chat"]["id"]
        user_id = str(msg["from"]["id"])
        text = msg["text"].strip()
        cmd = text.split()[0].lower() if text else ""

        sync_telegram_user(user_id, msg["from"].get("username"),
                           msg["from"].get("first_name"),
                           msg["from"].get("last_name"))

        session = get_session(user_id)
        if session and cmd != "/cancel" and not cmd.startswith("/"):
            handle_session_input(chat_id, user_id, text, session)
            return
        if session and cmd not in ("/cancel", "/start", "/menu"):
            if session.get("state") in ("create_key", "broadcast"):
                handle_session_input(chat_id, user_id, text, session)
                return

        if not cmd.startswith("/"):
            return

        handle_command(chat_id, user_id, text)

    except Exception as e:
        _bot_state["errors"] += 1
        _bot_state["last_error"] = str(e)
        print(f"[BOT] handle_update lỗi: {e}")
        traceback.print_exc()

# ============================================================
# WEBHOOK / POLLING
# ============================================================

def set_webhook_from_env():
    url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("WEBHOOK_URL")
    if not url or not BOT_TOKEN:
        print("[BOT] Không có URL, bỏ qua setWebhook.")
        return False
    webhook_url = f"{url}/webhook/{BOT_TOKEN}"
    ok = set_webhook(webhook_url, WEBHOOK_SECRET or None)
    print(f"[BOT] setWebhook: {'OK' if ok else 'FAIL'}")
    return ok

def polling_worker():
    offset = 0
    print("[BOT] Bắt đầu polling...")
    while True:
        try:
            res = tg_call("getUpdates", {
                "offset": offset,
                "timeout": 30,
                "allowed_updates": ["message", "callback_query"],
            }, timeout=40)
            if not res or not res.get("ok"):
                time.sleep(3)
                continue
            for upd in res.get("result", []):
                offset = upd["update_id"] + 1
                handle_update(upd)
        except Exception as e:
            print(f"[BOT] polling lỗi: {e}")
            time.sleep(5)

# ============================================================
# WORKERS
# ============================================================

def notify_worker():
    while True:
        try:
            flush_notify()
        except Exception as e:
            print(f"[BOT] notify_worker lỗi: {e}")
        time.sleep(10)

def cron_worker():
    while True:
        try:
            now = now_ms()
            rows = fetchall(
                "SELECT * FROM keys WHERE active = 1 AND expires_at > ? "
                "AND expires_at < ?",
                (now, now + 7 * 86400000),
            )
            for r in rows:
                uid = r["user_id"]
                if not uid: continue
                days_left = int((r["expires_at"] - now) / 86400000)
                if days_left in (7, 3, 1, 0):
                    push_notify(uid,
                        f"⚠️ Key <code>{esc(r['key'])}</code> còn {days_left} ngày.")
        except Exception as e:
            print(f"[BOT] cron_worker lỗi: {e}")
        time.sleep(3600)

def cleanup_worker():
    while True:
        try:
            sessions = read_json(SESSION_FILE, {})
            now = now_ms()
            clean = {k: v for k, v in sessions.items()
                     if now - v.get("updatedAt", 0) <= v.get("ttl", 300000)}
            if len(clean) != len(sessions):
                write_json(SESSION_FILE, clean)
        except Exception as e:
            print(f"[BOT] cleanup_worker lỗi: {e}")
        time.sleep(600)

def start_workers():
    threading.Thread(target=notify_worker, daemon=True).start()
    threading.Thread(target=cron_worker, daemon=True).start()
    threading.Thread(target=cleanup_worker, daemon=True).start()

# ============================================================
# ENTRY POINT - KHÔNG THOÁT KHI THIẾU TOKEN
# ============================================================

def check_bot():
    me = get_me()
    if me:
        print(f"[BOT] OK: @{me.get('username')}")
        return True
    print("[BOT] getMe thất bại.")
    return False

def wait_for_token():
    global BOT_TOKEN, API
    if BOT_TOKEN:
        return True
    print("[BOT] Thiếu BOT_TOKEN. Chờ biến môi trường (30s/lần)...")
    while not os.environ.get("BOT_TOKEN"):
        time.sleep(30)
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    API = f"https://api.telegram.org/bot{BOT_TOKEN}"
    print("[BOT] Đã nhận BOT_TOKEN.")
    return True

def main():
    ensure_dir(DATA_DIR)
    wait_for_token()

    attempt = 0
    while not check_bot():
        attempt += 1
        print(f"[BOT] Token chưa hợp lệ (lần {attempt}). Thử lại sau 30s...")
        time.sleep(30)

    start_workers()

    use_webhook = os.environ.get("USE_WEBHOOK", "false").lower() == "true"
    if use_webhook:
        set_webhook_from_env()
        print("[BOT] Đang chạy webhook. Giữ process sống.")
        while True:
            time.sleep(3600)
    else:
        polling_worker()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[BOT] Dừng theo yêu cầu.")
    except Exception as e:
        print(f"[BOT] Lỗi nghiêm trọng: {e}")
        traceback.print_exc()
        while True:
            time.sleep(3600)
