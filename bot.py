# bot.py - Telegram Bot + Web Server tích hợp
# Tác giả: MADE BY Bao Huy
# Chạy: python bot.py
# Yêu cầu: key.py, auth.py, apikey.py, db.py
# Không cần app.py riêng

import os
import sys
import json
import time
import html
import secrets
import threading
import traceback
from datetime import datetime

import requests

# ============================================================
# IMPORT MODULE NỘI BỘ
# ============================================================

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
    print("[BOT] Cần có: key.py, auth.py, apikey.py, db.py cùng thư mục")
    # Không thoát - vẫn chạy HTTP server để Render không báo lỗi port
    keymod = None
    authmod = None
    apikey = None

# ============================================================
# CẤU HÌNH
# ============================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

ADMIN_IDS = set(
    x.strip() for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()
)

DEFAULT_DAYS = 30
DEFAULT_MAX_DEVICES = 1

if keymod:
    DEFAULT_DAYS = getattr(keymod, "DEFAULT_DAYS", 30)
    DEFAULT_MAX_DEVICES = getattr(keymod, "DEFAULT_MAX_DEVICES", 1)

AUTO_ISSUE_ENABLED = os.environ.get("AUTO_ISSUE_ENABLED", "true").lower() == "true"
AUTO_ISSUE_ONCE = os.environ.get("AUTO_ISSUE_ONCE", "true").lower() == "true"
CTV_MAX_DAYS = int(os.environ.get("CTV_MAX_DAYS", "30"))
CTV_MAX_KEYS = int(os.environ.get("CTV_MAX_KEYS", "50"))
BROADCAST_DELAY = float(os.environ.get("BROADCAST_DELAY", "0.05"))
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

if keymod:
    DATA_DIR = getattr(keymod, "DATA_DIR", "./data")
else:
    DATA_DIR = os.environ.get("DATA_DIR", "./data")

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

def send_inline_keyboard(chat_id, text, buttons, parse_mode="HTML"):
    return send_message(chat_id, text, parse_mode=parse_mode,
                        reply_markup={"inline_keyboard": buttons})

def answer_callback(cb_id, text="", show_alert=False):
    tg_call("answerCallbackQuery", {
        "callback_query_id": cb_id,
        "text": truncate(text, 200),
        "show_alert": show_alert,
    })

def get_me():
    res = tg_call("getMe", {}, timeout=10)
    if res and res.get("ok"):
        return res.get("result")
    return None

# ============================================================
# CTV
# ============================================================

def is_ctv(user_id):
    if not keymod:
        return False
    try:
        row = fetchone("SELECT user_id FROM ctv WHERE user_id = ? AND active = 1",
                       (str(user_id),))
        return row is not None
    except Exception:
        return False

def is_admin(user_id):
    return str(user_id) in ADMIN_IDS

def get_ctv(user_id):
    try:
        row = fetchone("SELECT * FROM ctv WHERE user_id = ?", (str(user_id),))
        return dict(row) if row else None
    except Exception:
        return None

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
    try:
        execute("UPDATE ctv SET keys_created = keys_created + 1 WHERE user_id = ?",
                (str(user_id),))
    except Exception:
        pass

# ============================================================
# USER / KEY
# ============================================================

def get_key_by_user(user_id):
    try:
        row = fetchone(
            "SELECT key FROM keys WHERE user_id = ? AND active = 1 "
            "ORDER BY created_at DESC LIMIT 1", (str(user_id),))
        return row["key"] if row else None
    except Exception:
        return None

def link_key_to_user(user_id, key):
    try:
        execute("UPDATE keys SET user_id = ? WHERE key = ?", (str(user_id), key))
    except Exception:
        pass

def get_or_create_key_for_user(user_id, owner=None, days=None,
                                max_devices=None, created_by=None):
    if not keymod:
        return {"created": False, "key": None, "error": "module key lỗi"}

    uid = str(user_id)
    if AUTO_ISSUE_ONCE:
        existing = get_key_by_user(uid)
        if existing:
            try:
                row = fetchone("SELECT * FROM keys WHERE key = ?", (existing,))
                if row and row["active"] and now_ms() < row["expires_at"]:
                    return {"created": False, "key": existing, "record": dict(row)}
            except Exception:
                pass

    days = days if days is not None else DEFAULT_DAYS
    owner = owner or f"user_{uid}"
    max_devices = max_devices if max_devices is not None else DEFAULT_MAX_DEVICES

    try:
        k, exp, sig = keymod.create_key(
            days, owner, max_devices, user_id=uid, created_by=created_by)
        link_key_to_user(uid, k)
        return {"created": True, "key": k, "expiresAt": exp, "signature": sig}
    except Exception as e:
        print(f"[BOT] create_key lỗi: {e}")
        return {"created": False, "key": None, "error": str(e)}

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

def get_telegram_user(user_id):
    return read_json(TG_USERS_FILE, {}).get(str(user_id))

def list_telegram_users():
    return read_json(TG_USERS_FILE, {})

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
    if admin:
        buttons.append([{"text": "📊 Thống kê", "callback_data": "stats"}])
    send_inline_keyboard(chat_id, "<b>MENU CHÍNH</b>", buttons)

# ============================================================
# CALLBACK HANDLER
# ============================================================

def handle_callback(cb):
    cb_id = cb.get("id")
    chat_id = cb["message"]["chat"]["id"]
    user_id = str(cb["from"]["id"])
    data = cb.get("data", "")

    if data == "menu":
        answer_callback(cb_id)
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
        info = keymod.get_key_info(k) if keymod else None
        if not info:
            send_message(chat_id, "Key không tồn tại.")
            return
        send_message(chat_id,
            f"<code>{esc(k)}</code>\n"
            f"Còn: {info['daysLeft']} ngày\n"
            f"TB: {info['devicesUsed']}/{info['maxDevices']}")
        return
    if data == "my_devices":
        answer_callback(cb_id)
        k = get_key_by_user(user_id)
        if not k:
            send_message(chat_id, "Chưa có key.")
            return
        rows = fetchall("SELECT * FROM devices WHERE key = ? LIMIT 20", (k,))
        if not rows:
            send_message(chat_id, "Chưa có thiết bị.")
            return
        lines = ["<b>THIẾT BỊ</b>"]
        for r in rows:
            lines.append(f"<code>{esc(r['device_id'])}</code> | {esc(r['ip'])}")
        send_message(chat_id, "\n".join(lines))
        return
    if data == "my_info":
        answer_callback(cb_id)
        tg = get_telegram_user(user_id) or {}
        k = get_key_by_user(user_id)
        role = "admin" if is_admin(user_id) else "ctv" if is_ctv(user_id) else "user"
        send_message(chat_id,
            f"ID: <code>{esc(user_id)}</code>\n"
            f"Username: @{esc(tg.get('username', '-'))}\n"
            f"Vai trò: {role}\n"
            f"Key: <code>{esc(k or 'chưa có')}</code>")
        return
    if data == "stats":
        answer_callback(cb_id)
        cmd_stats(chat_id, user_id)
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
        if keymod:
            try:
                lines = keymod.render_tree_text(keymod.build_tree_view())
                send_message(chat_id, "🌳\n" + ("\n".join(lines) if lines else "Chưa có key."))
            except Exception:
                send_message(chat_id, "Lỗi cây key.")
        return

    answer_callback(cb_id, "Không hỗ trợ")

# ============================================================
# COMMAND HANDLERS
# ============================================================

def cmd_stats(chat_id, user_id):
    if not is_admin(user_id):
        send_message(chat_id, "Không có quyền.")
        return
    try:
        row = fetchone("""
            SELECT
              (SELECT COUNT(*) FROM keys) AS total,
              (SELECT COUNT(*) FROM keys WHERE active=1) AS active,
              (SELECT COUNT(*) FROM devices) AS devices,
              (SELECT COUNT(*) FROM accounts) AS accounts,
              (SELECT COUNT(*) FROM ctv) AS ctv
        """)
        send_message(chat_id,
            f"<b>THỐNG KÊ</b>\n"
            f"Tổng key: {row['total']}\n"
            f"Hoạt động: {row['active']}\n"
            f"Thiết bị: {row['devices']}\n"
            f"Tài khoản: {row['accounts']}\n"
            f"CTV: {row['ctv']}")
    except Exception as e:
        send_message(chat_id, f"Lỗi: {e}")

def cmd_botstats(chat_id, user_id):
    if not is_admin(user_id):
        send_message(chat_id, "Không có quyền.")
        return
    up = now_ms() - _bot_state["started_at"]
    me = get_me()
    send_message(chat_id,
        f"<b>BOT STATS</b>\n"
        f"Uptime: {humanize_delta(up)}\n"
        f"Updates: {_bot_state['updates_handled']}\n"
        f"Commands: {_bot_state['commands_handled']}\n"
        f"Errors: {_bot_state['errors']}\n"
        f"Bot: @{esc((me or {}).get('username', '-'))}\n"
        f"Users: {len(list_telegram_users())}")

# ============================================================
# SESSION INPUT
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
            max_dev = parse_int(text, 1) or 1
            days = data.get("days", 30)
            owner = data.get("owner", "unknown")
            if keymod:
                try:
                    k, exp, sig = keymod.create_key(days, owner, max_dev)
                    send_message(chat_id, f"<code>{esc(k)}</code>")
                except Exception as e:
                    send_message(chat_id, f"Lỗi: {e}")
            clear_session(user_id)
            return

    clear_session(user_id)
    send_message(chat_id, "Phiên đã kết thúc.")

# ============================================================
# COMMAND HANDLER
# ============================================================

def handle_command(chat_id, user_id, text):
    parts = text.split()
    cmd = parts[0].lower()
    admin = is_admin(user_id)
    ctv = is_ctv(user_id)

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
        if result.get("key"):
            send_message(chat_id,
                f"{'Đã cấp' if result['created'] else 'Đã có'} key:\n"
                f"<code>{esc(result['key'])}</code>")
        else:
            send_message(chat_id, f"Lỗi: {result.get('error', 'không rõ')}")
        return
    if cmd == "/mykey":
        k = get_key_by_user(user_id)
        if not k:
            send_message(chat_id, "Chưa có key. Dùng /code.")
            return
        info = keymod.get_key_info(k) if keymod else None
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
            f"Username: @{esc(tg.get('username', '-'))}\n"
            f"Vai trò: {role}\n"
            f"Key: <code>{esc(k or 'chưa có')}</code>")
        return
    if cmd == "/stats":
        cmd_stats(chat_id, user_id)
        return
    if cmd == "/botstats":
        cmd_botstats(chat_id, user_id)
        return
    if cmd == "/health":
        send_message(chat_id,
            f"Uptime: {humanize_delta(now_ms() - _bot_state['started_at'])}\n"
            f"Errors: {_bot_state['errors']}")
        return
    if cmd == "/cancel":
        clear_session(user_id)
        send_message(chat_id, "Đã hủy.")
        return

    send_message(chat_id, f"Lệnh không hỗ trợ: {esc(cmd)}")

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
                           msg["from"].get("first_name"))
        session = get_session(user_id)
        if session and cmd != "/cancel" and not cmd.startswith("/"):
            handle_session_input(chat_id, user_id, text, session)
            return
        if cmd.startswith("/"):
            handle_command(chat_id, user_id, text)
    except Exception as e:
        _bot_state["errors"] += 1
        _bot_state["last_error"] = str(e)
        print(f"[BOT] handle_update lỗi: {e}")

# ============================================================
# POLLING WORKER
# ============================================================

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

def notify_worker():
    while True:
        try:
            flush_notify()
        except Exception as e:
            print(f"[BOT] notify_worker lỗi: {e}")
        time.sleep(10)

def start_workers():
    threading.Thread(target=notify_worker, daemon=True).start()

# ============================================================
# HTTP SERVER - CHẠY SONG SONG VỚI BOT
# ============================================================

def run_http_server():
    """Chạy Flask trong thread riêng để Render detect port."""
    try:
        from flask import Flask, jsonify, request
    except ImportError:
        print("[HTTP] Flask không có, không mở port")
        return

    app = Flask(__name__)

    # ---------------- ROUTE CƠ BẢN ----------------

    @app.route("/")
    def index():
        return "Key Server OK"

    @app.route("/ping")
    def ping():
        return "pong"

    @app.route("/health")
    def health():
        return jsonify({
            "ok": True,
            "service": "key-server",
            "bot": "running" if BOT_TOKEN else "no-token",
            "uptime": now_ms() - _bot_state["started_at"],
            "updates": _bot_state["updates_handled"],
            "commands": _bot_state["commands_handled"],
            "errors": _bot_state["errors"],
            "port": os.environ.get("PORT", "10000"),
        })

    @app.route("/status")
    def status_page():
        me = get_me()
        up = humanize_delta(now_ms() - _bot_state["started_at"])
        html_page = f"""<!DOCTYPE html>
        <html><head><meta charset="utf-8"><title>Status</title>
        <style>
            body{{font-family:monospace;background:#0d1117;color:#c9d1d9;padding:20px}}
            h1{{color:#58a6ff}}
            table{{border-collapse:collapse;margin-top:10px}}
            td,th{{border:1px solid #30363d;padding:8px 12px}}
            th{{background:#21262d;color:#58a6ff}}
            .ok{{color:#3fb950}}
        </style></head><body>
        <h1>🔑 KEY SERVER STATUS</h1>
        <table>
            <tr><th>Thuộc tính</th><th>Giá trị</th></tr>
            <tr><td>Uptime</td><td class="ok">{up}</td></tr>
            <tr><td>Bot</td><td class="ok">@{esc((me or {}).get('username', '-'))}</td></tr>
            <tr><td>Updates</td><td>{_bot_state['updates_handled']}</td></tr>
            <tr><td>Commands</td><td>{_bot_state['commands_handled']}</td></tr>
            <tr><td>Errors</td><td>{_bot_state['errors']}</td></tr>
            <tr><td>Users</td><td>{len(list_telegram_users())}</td></tr>
            <tr><td>Port</td><td>{os.environ.get('PORT', '10000')}</td></tr>
        </table></body></html>"""
        return html_page

    # ---------------- WEBHOOK TELEGRAM ----------------

    @app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
    def webhook():
        try:
            data = request.get_json(force=True, silent=True) or {}
            handle_update(data)
        except Exception as e:
            print(f"[HTTP] webhook lỗi: {e}")
        return "OK", 200

    @app.route("/webhook", methods=["POST"])
    def webhook_noprefix():
        try:
            data = request.get_json(force=True, silent=True) or {}
            handle_update(data)
        except Exception as e:
            print(f"[HTTP] webhook lỗi: {e}")
        return "OK", 200

    # ---------------- ĐĂNG KÝ WEB/API BLUEPRINT ----------------

    try:
        import web
        web.register(app)
        print("[HTTP] Đã đăng ký web blueprint")
    except Exception as e:
        print(f"[HTTP] web blueprint lỗi: {e}")

    try:
        import api
        api.register(app)
        print("[HTTP] Đã đăng ký api blueprint")
    except Exception as e:
        print(f"[HTTP] api blueprint lỗi: {e}")

    # ---------------- CHẠY ----------------

    port = int(os.environ.get("PORT", 10000))
    host = "0.0.0.0"
    print(f"[HTTP] Flask chạy trên {host}:{port}")
    app.run(host=host, port=port, threaded=True, use_reloader=False, debug=False)

# ============================================================
# ENTRY POINT
# ============================================================

def wait_for_token():
    global BOT_TOKEN, API
    if BOT_TOKEN:
        return True
    print("[BOT] Thiếu BOT_TOKEN. Chờ biến môi trường...")
    while not os.environ.get("BOT_TOKEN"):
        time.sleep(30)
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    API = f"https://api.telegram.org/bot{BOT_TOKEN}"
    print("[BOT] Đã nhận BOT_TOKEN.")
    return True

def check_bot():
    me = get_me()
    if me:
        print(f"[BOT] OK: @{me.get('username')}")
        return True
    print("[BOT] getMe thất bại.")
    return False

def main():
    ensure_dir(DATA_DIR)
    print(f"[BOT] Python: {sys.version.split()[0]}")
    print(f"[BOT] PORT: {os.environ.get('PORT', '10000')}")
    print(f"[BOT] DATA_DIR: {DATA_DIR}")
    print(f"[BOT] BOT_TOKEN: {'SET' if BOT_TOKEN else 'MISSING'}")

    # Luôn mở HTTP server trước để Render detect port
    http_thread = threading.Thread(target=run_http_server,
                                    daemon=True, name="http-server")
    http_thread.start()
    print("[BOT] Đã khởi động HTTP server thread")
    time.sleep(1)  # Cho Flask kịp bind port

    # Nếu không có token, chỉ chạy HTTP
    if not BOT_TOKEN:
        print("[BOT] Không có BOT_TOKEN, chỉ chạy HTTP server.")
        while True:
            time.sleep(3600)

    wait_for_token()

    # Kiểm tra bot, retry thay vì thoát
    while not check_bot():
        print("[BOT] Token chưa hợp lệ. Thử lại sau 30s...")
        time.sleep(30)

    start_workers()

    use_webhook = os.environ.get("USE_WEBHOOK", "false").lower() == "true"
    if use_webhook:
        url = os.environ.get("RENDER_EXTERNAL_URL", "")
        if url:
            webhook_url = f"{url}/webhook/{BOT_TOKEN}"
            payload = {
                "url": webhook_url,
                "drop_pending_updates": "true",
                "allowed_updates": json.dumps(["message", "callback_query"]),
            }
            if WEBHOOK_SECRET:
                payload["secret_token"] = WEBHOOK_SECRET
            r = tg_call("setWebhook", payload)
            print(f"[BOT] setWebhook: {r}")
        print("[BOT] Chạy chế độ webhook. Giữ process sống.")
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
