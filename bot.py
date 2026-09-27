# bot.py - Telegram Bot + Web Server + API + Login Key
# Tác giả: MADE BY Bao Huy
# Chạy: python bot.py
# Yêu cầu: key.py, auth.py, apikey.py, db.py cùng thư mục

import os
import sys
import json
import time
import html
import hashlib
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
    keymod = None
    authmod = None
    apikey = None

    def now_ms():
        return int(time.time() * 1000)

    def fmt_time(ms):
        try:
            return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return "-"

    def fetchone(*a, **k):
        return None

    def fetchall(*a, **k):
        return []

    def execute(*a, **k):
        return None

    def insert(*a, **k):
        return None

    def update(*a, **k):
        return 0

    def delete(*a, **k):
        return 0

# ============================================================
# CẤU HÌNH
# ============================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

ADMIN_IDS = set(
    x.strip() for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()
)

DEFAULT_DAYS = getattr(keymod, "DEFAULT_DAYS", 30) if keymod else 30
DEFAULT_MAX_DEVICES = getattr(keymod, "DEFAULT_MAX_DEVICES", 1) if keymod else 1

AUTO_ISSUE_ENABLED = os.environ.get("AUTO_ISSUE_ENABLED", "true").lower() == "true"
AUTO_ISSUE_ONCE = os.environ.get("AUTO_ISSUE_ONCE", "true").lower() == "true"
CTV_MAX_DAYS = int(os.environ.get("CTV_MAX_DAYS", "30"))
CTV_MAX_KEYS = int(os.environ.get("CTV_MAX_KEYS", "50"))
BROADCAST_DELAY = float(os.environ.get("BROADCAST_DELAY", "0.05"))
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

DATA_DIR = getattr(keymod, "DATA_DIR", "./data") if keymod else os.environ.get("DATA_DIR", "./data")
SESSION_FILE = os.path.join(DATA_DIR, "bot_sessions.json")
NOTIFY_FILE = os.path.join(DATA_DIR, "notify_queue.json")
TG_USERS_FILE = os.path.join(DATA_DIR, "telegram_users.json")

_bot_state = {
    "started_at": now_ms(),
    "updates_handled": 0,
    "commands_handled": 0,
    "callbacks_handled": 0,
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
# CTV / USER
# ============================================================

def is_ctv(user_id):
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
        k, exp, sig = keymod.create_key(days, owner, max_devices,
                                         user_id=uid, created_by=created_by)
        link_key_to_user(uid, k)
        return {"created": True, "key": k, "expiresAt": exp, "signature": sig}
    except Exception as e:
        print(f"[BOT] create_key lỗi: {e}")
        return {"created": False, "key": None, "error": str(e)}

# ============================================================
# SESSION / NOTIFY
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
    write_json(TG_USERS_FILE, users)

def list_telegram_users():
    return read_json(TG_USERS_FILE, {})

def count_telegram_users():
    return len(list_telegram_users())

# ============================================================
# HELP & MENU BOT
# ============================================================

HELP_TEXT = """
🔑 <b>KEY SERVER BOT</b>

<b>Người dùng:</b>
/start /menu /help
/code - Nhận key
/mykey /myinfo
/verify &lt;key&gt; &lt;device&gt;
/info &lt;key&gt; /days &lt;key&gt;

<b>Admin:</b>
/stats /botstats /health /broadcast
""".strip()

def cmd_menu(chat_id, user_id):
    admin = is_admin(user_id)
    buttons = [
        [{"text": "🔑 Key của tôi", "callback_data": "my_key"},
         {"text": "ℹ️ Thông tin", "callback_data": "my_info"}],
        [{"text": "📖 Trợ giúp", "callback_data": "help"}],
    ]
    if admin:
        buttons.append([{"text": "📊 Thống kê", "callback_data": "stats"}])
    send_inline_keyboard(chat_id, "<b>MENU CHÍNH</b>", buttons)

def handle_callback(cb):
    cb_id = cb.get("id")
    chat_id = cb["message"]["chat"]["id"]
    user_id = str(cb["from"]["id"])
    data = cb.get("data", "")
    _bot_state["callbacks_handled"] += 1

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
    if data == "my_info":
        answer_callback(cb_id)
        k = get_key_by_user(user_id)
        role = "admin" if is_admin(user_id) else "ctv" if is_ctv(user_id) else "user"
        send_message(chat_id,
            f"ID: <code>{esc(user_id)}</code>\n"
            f"Vai trò: {role}\n"
            f"Key: <code>{esc(k or 'chưa có')}</code>")
        return
    if data == "stats":
        answer_callback(cb_id)
        cmd_stats(chat_id, user_id)
        return
    answer_callback(cb_id, "Không hỗ trợ")

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
              (SELECT COUNT(*) FROM accounts) AS accounts
        """)
        send_message(chat_id,
            f"<b>THỐNG KÊ</b>\n"
            f"Tổng key: {row['total']}\n"
            f"Hoạt động: {row['active']}\n"
            f"Thiết bị: {row['devices']}\n"
            f"Tài khoản: {row['accounts']}")
    except Exception as e:
        send_message(chat_id, f"Lỗi: {e}")

def handle_command(chat_id, user_id, text):
    parts = text.split()
    cmd = parts[0].lower()
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
        send_message(chat_id, f"<code>{esc(k)}</code>")
        return
    if cmd == "/stats":
        cmd_stats(chat_id, user_id)
        return
    if cmd == "/health":
        ok = False
        try:
            ok = fetchone("SELECT 1 AS x") is not None
        except Exception:
            pass
        send_message(chat_id,
            f"DB: {'OK' if ok else 'FAIL'}\n"
            f"Uptime: {humanize_delta(now_ms() - _bot_state['started_at'])}")
        return
    send_message(chat_id, f"Lệnh không hỗ trợ: {esc(cmd)}")

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
        if cmd.startswith("/"):
            handle_command(chat_id, user_id, text)
    except Exception as e:
        _bot_state["errors"] += 1
        print(f"[BOT] handle_update lỗi: {e}")

def polling_worker():
    offset = 0
    print("[BOT] Bắt đầu polling...")
    while True:
        try:
            res = tg_call("getUpdates", {
                "offset": offset, "timeout": 30,
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
        except Exception:
            pass
        time.sleep(10)

def start_workers():
    threading.Thread(target=notify_worker, daemon=True).start()

# ============================================================
# WEB + API SERVER
# ============================================================

def run_http_server():
    try:
        from flask import (Flask, jsonify, request, make_response,
                            redirect, render_template_string)
    except ImportError:
        print("[HTTP] Flask không có, không mở port")
        return

    app = Flask(__name__)

    CSS = """
    <style>
      *{box-sizing:border-box}
      body{background:#0d1117;color:#c9d1d9;font-family:monospace;margin:0;padding:12px}
      h1,h2{color:#58a6ff;margin:8px 0}
      h1{font-size:20px}
      .box{border:1px solid #30363d;padding:14px;margin:10px 0;border-radius:8px;background:#161b22}
      input,button,select,textarea{background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:8px;font-family:monospace;border-radius:4px;width:100%;margin:4px 0;font-size:13px}
      button{background:#238636;cursor:pointer;color:#fff}
      button:hover{background:#2ea043}
      button.danger{background:#da3633}
      button.neutral{background:#30363d}
      a{color:#58a6ff;text-decoration:none}
      a:hover{text-decoration:underline}
      .err{color:#f85149;font-size:12px;margin-top:6px}
      .ok{color:#3fb950;font-size:12px;margin-top:6px}
      .key{color:#3fb950;word-break:break-all;font-size:13px}
      .muted{color:#8b949e;font-size:12px}
      .nav{display:flex;gap:8px;padding:8px 10px;background:#161b22;border:1px solid #30363d;border-radius:8px;margin-bottom:10px;font-size:13px;align-items:center;flex-wrap:wrap}
      .nav a{padding:5px 10px;border-radius:4px;background:#21262d}
      .nav .brand{color:#58a6ff;font-weight:bold}
      .wrap{max-width:420px;margin:60px auto}
      table{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}
      th,td{border:1px solid #30363d;padding:6px;text-align:left;word-break:break-all}
      th{background:#21262d;color:#58a6ff}
      .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px}
      .stat{border:1px solid #30363d;padding:10px;border-radius:6px;background:#0d1117;font-size:12px}
      .stat b{color:#58a6ff;font-size:18px;display:block;margin-top:4px}
      .row{display:flex;gap:8px;flex-wrap:wrap;align-items:flex-start}
      .row > *{flex:1;min-width:100px}
      .tag{display:inline-block;padding:2px 6px;border-radius:4px;font-size:11px;background:#21262d;color:#8b949e}
      .tag.admin{background:#3a2a00;color:#f0883e}
      .tag.user{background:#0d2818;color:#3fb950}
      .on{color:#3fb950}.off{color:#f85149}
    </style>
    """

    def page(title, body):
        return f"""<!DOCTYPE html><html lang="vi"><head>
        <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>{title}</title>{CSS}</head><body>{body}</body></html>"""

    def nav(me):
        if me:
            role_cls = "admin" if me["role"] == "admin" else "user"
            me_tag = (f'<span class="tag {role_cls}">{esc(me["username"])} '
                      f'({esc(me["role"])})</span>'
                      f'<a href="/keys">Keys</a>'
                      f'<a href="/create">Tạo key</a>'
                      f'<a href="/api">API</a>'
                      f'<a href="/logout">Thoát</a>')
        else:
            me_tag = '<a href="/login">Đăng nhập</a>'
        return (f'<div class="nav"><span class="brand">🔑 KEY SERVER</span>'
                f'<span style="flex:1"></span>{me_tag}</div>')

    # ---------------- AUTH HELPERS ----------------

    def hash_password(password, salt=None):
        if not salt:
            salt = secrets.token_hex(16)
        h = hashlib.sha256((salt + password).encode()).hexdigest()
        return f"{salt}${h}"

    def check_password(password, stored):
        try:
            salt, h = stored.split("$", 1)
            return hashlib.sha256((salt + password).encode()).hexdigest() == h
        except Exception:
            return False

    def get_account_by_uid(uid):
        try:
            return fetchone("SELECT * FROM accounts WHERE uid = ?", (uid,))
        except Exception:
            return None

    def get_account_by_username(username):
        try:
            return fetchone("SELECT * FROM accounts WHERE username = ?", (username,))
        except Exception:
            return None

    def create_token(uid):
        token = secrets.token_urlsafe(32)
        try:
            execute(
                "INSERT OR REPLACE INTO sessions "
                "(token, uid, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, uid, now_ms(), now_ms() + 7 * 86400000),
            )
        except Exception:
            pass
        return token

    def uid_from_token(token):
        if not token:
            return None
        try:
            row = fetchone(
                "SELECT uid FROM sessions WHERE token = ? AND expires_at > ?",
                (token, now_ms()))
            return row["uid"] if row else None
        except Exception:
            return None

    def destroy_token(token):
        try:
            execute("DELETE FROM sessions WHERE token = ?", (token,))
        except Exception:
            pass

    def current_user():
        uid = uid_from_token(request.cookies.get("session"))
        if not uid:
            return None
        rec = get_account_by_uid(uid)
        if not rec:
            return None
        return {
            "uid": uid, "username": rec["username"],
            "role": rec["role"] or "user",
        }

    def require_login(f):
        def wrapper(*args, **kwargs):
            me = current_user()
            if not me:
                return redirect("/login")
            return f(me, *args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper

    # ---------------- LOGIN / REGISTER ----------------

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = ""
        if request.method == "POST":
            u = request.form.get("username", "").strip()
            p = request.form.get("password", "")
            rec = get_account_by_username(u)
            if not rec or not rec["password_hash"] or \
               not check_password(p, rec["password_hash"]):
                error = "Sai tài khoản hoặc mật khẩu."
            elif not rec["active"]:
                error = "Tài khoản đã bị khóa."
            else:
                token = create_token(rec["uid"])
                resp = make_response(redirect("/my"))
                resp.set_cookie("session", token, httponly=True,
                                samesite="Lax", max_age=604800)
                return resp
        body = f"""
        <div class="wrap"><div class="box">
        <h1>🔑 ĐĂNG NHẬP KEY</h1>
        <form method="POST">
            <input name="username" placeholder="tài khoản">
            <input name="password" type="password" placeholder="mật khẩu">
            <div class="err">{error}</div>
            <button type="submit">Đăng nhập</button>
        </form>
        <div class="muted" style="text-align:center;margin-top:10px">
            Chưa có tài khoản? <a href="/register">Đăng ký</a>
        </div>
        </div></div>"""
        return page("Đăng nhập", body)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        error = ""
        if request.method == "POST":
            u = request.form.get("username", "").strip()
            p = request.form.get("password", "")
            p2 = request.form.get("password2", "")
            if len(u) < 3:
                error = "Tài khoản phải từ 3 ký tự."
            elif len(p) < 6:
                error = "Mật khẩu phải từ 6 ký tự."
            elif p != p2:
                error = "Mật khẩu nhập lại không khớp."
            elif get_account_by_username(u):
                error = "Tài khoản đã tồn tại."
            else:
                uid = secrets.token_hex(8)
                pw_hash = hash_password(p)
                try:
                    execute(
                        "INSERT INTO accounts "
                        "(uid, username, password_hash, role, active, created_at) "
                        "VALUES (?, ?, ?, 'user', 1, ?)",
                        (uid, u, pw_hash, now_ms()))
                    token = create_token(uid)
                    resp = make_response(redirect("/my"))
                    resp.set_cookie("session", token, httponly=True,
                                    samesite="Lax", max_age=604800)
                    return resp
                except Exception as e:
                    error = f"Lỗi: {e}"
        body = f"""
        <div class="wrap"><div class="box">
        <h1>🔑 ĐĂNG KÝ</h1>
        <form method="POST">
            <input name="username" placeholder="tài khoản (≥3)">
            <input name="password" type="password" placeholder="mật khẩu (≥6)">
            <input name="password2" type="password" placeholder="nhập lại mật khẩu">
            <div class="err">{error}</div>
            <button type="submit">Đăng ký</button>
        </form>
        <div class="muted" style="text-align:center;margin-top:10px">
            Đã có tài khoản? <a href="/login">Đăng nhập</a>
        </div>
        </div></div>"""
        return page("Đăng ký", body)

    @app.route("/logout")
    def logout():
        destroy_token(request.cookies.get("session"))
        resp = make_response(redirect("/login"))
        resp.set_cookie("session", "", max_age=0)
        return resp

    # ---------------- MY PANEL ----------------

    @app.route("/my")
    @require_login
    def my_panel(me):
        rec = get_account_by_uid(me["uid"])
        my_key = rec["key"] if rec else None
        key_html = ""
        if my_key and keymod:
            try:
                info = keymod.get_key_info(my_key)
                if info:
                    key_html = f"""
                    <div class="key"><code>{esc(info['key'])}</code></div>
                    <div>Chủ: {esc(info['owner'])}</div>
                    <div>Hết hạn: {esc(info.get('expiresAtText', '-'))}</div>
                    <div>Còn: {info.get('daysLeft', 0)} ngày</div>
                    <div>TB: {info.get('devicesUsed', 0)}/{info.get('maxDevices', 1)}</div>
                    """
            except Exception:
                pass
        if not key_html:
            key_html = """
            <div class="muted">Bạn chưa có key.</div>
            <form method="POST" action="/my/getkey">
                <button type="submit">NHẬN KEY</button>
            </form>"""

        success = request.args.get("success", "")
        error = request.args.get("error", "")
        body = nav(me) + f"""
        <div class="box">
            <h1>XIN CHÀO {esc(me['username'])}</h1>
            <div class="muted">Vai trò: {esc(me['role'])}</div>
        </div>
        <div class="box"><h2>KEY CỦA BẠN</h2>{key_html}</div>
        <div class="box"><h2>ĐỔI MẬT KHẨU</h2>
            <form method="POST" action="/my/changepw">
                <input name="old_password" type="password" placeholder="mật khẩu cũ">
                <input name="new_password" type="password" placeholder="mật khẩu mới">
                <button type="submit">Đổi mật khẩu</button>
            </form>
            <div class="err">{error}</div>
            <div class="ok">{success}</div>
        </div>"""
        return page("Cá nhân", body)

    @app.route("/my/getkey", methods=["POST"])
    @require_login
    def my_getkey(me):
        if not keymod:
            return redirect("/my?error=Module+key+lỗi")
        rec = get_account_by_uid(me["uid"])
        try:
            k, exp, sig = keymod.create_key(
                DEFAULT_DAYS, rec["username"], DEFAULT_MAX_DEVICES,
                user_id=me["uid"])
            execute("UPDATE accounts SET key = ? WHERE uid = ?", (k, me["uid"]))
            notify_key_created(k, rec["username"], DEFAULT_DAYS, by=me["username"])
        except Exception as e:
            return redirect(f"/my?error=Lỗi+tạo+key")
        return redirect("/my?success=Đã+cấp+key")

    @app.route("/my/changepw", methods=["POST"])
    @require_login
    def my_changepw(me):
        old = request.form.get("old_password", "")
        new = request.form.get("new_password", "")
        rec = get_account_by_uid(me["uid"])
        if not rec or not check_password(old, rec["password_hash"] or ""):
            return redirect("/my?error=Mật+khẩu+cũ+không+đúng")
        if len(new) < 6:
            return redirect("/my?error=Mật+khẩu+mới+quá+ngắn")
        execute("UPDATE accounts SET password_hash = ? WHERE uid = ?",
                (hash_password(new), me["uid"]))
        return redirect("/my?success=Đã+đổi+mật+khẩu")

    # ---------------- KEYS LIST ----------------

    @app.route("/keys")
    @require_login
    def keys_list(me):
        rows = []
        try:
            rows = fetchall("SELECT * FROM keys ORDER BY created_at DESC LIMIT 100")
        except Exception:
            pass
        now = now_ms()
        trs = ""
        for r in rows:
            days_left = max(0, int((r["expires_at"] - now) / 86400000))
            trs += f"""<tr>
              <td><code class="key">{esc(r['key'])}</code></td>
              <td>{esc(r['owner'])}</td>
              <td class="{'on' if r['active'] else 'off'}">{'ON' if r['active'] else 'OFF'}</td>
              <td>{days_left}d</td>
              <td>{fmt_time(r['expires_at'])}</td>
            </tr>"""
        body = nav(me) + f"""
        <div class="box"><h1>DANH SÁCH KEY</h1>
          <a href="/create"><button>Tạo key mới</button></a>
          <table><tr><th>Key</th><th>Chủ</th><th>Trạng thái</th><th>Còn</th><th>Hết hạn</th></tr>
          {trs or '<tr><td colspan="5" class="muted">Chưa có key.</td></tr>'}
          </table>
        </div>"""
        return page("Keys", body)

    # ---------------- CREATE KEY ----------------

    @app.route("/create", methods=["GET", "POST"])
    @require_login
    def create_page(me):
        result_html = ""
        error = ""
        if request.method == "POST":
            days = parse_int(request.form.get("days", 30), 30)
            owner = request.form.get("owner", "").strip() or me["username"]
            max_dev = parse_int(request.form.get("max_devices", 1), 1)
            if days <= 0 or days > 3650:
                error = "Số ngày không hợp lệ."
            elif max_dev <= 0 or max_dev > 1000:
                error = "Max thiết bị không hợp lệ."
            elif not keymod:
                error = "Module key lỗi."
            else:
                try:
                    k, exp, sig = keymod.create_key(days, owner, max_dev,
                                                     created_by=me["username"])
                    notify_key_created(k, owner, days, by=me["username"])
                    result_html = f"""
                    <div class="box">
                      <h2>✅ KEY ĐÃ TẠO</h2>
                      <div class="key"><code>{esc(k)}</code></div>
                      <div>Chủ: {esc(owner)}</div>
                      <div>Hạn: {days} ngày</div>
                      <div>Hết hạn: {esc(fmt_time(exp))}</div>
                      <div>Max TB: {max_dev}</div>
                    </div>"""
                except Exception as e:
                    error = f"Lỗi tạo key: {e}"
        body = nav(me) + f"""
        <div class="box"><h1>TẠO KEY MỚI</h1>
        <form method="POST">
            <div class="row">
              <input name="days" value="30" placeholder="số ngày">
              <input name="owner" value="{esc(me['username'])}" placeholder="chủ sở hữu">
              <input name="max_devices" value="1" placeholder="max thiết bị">
            </div>
            <button type="submit">Tạo key</button>
        </form>
        <div class="err">{error}</div>
        </div>
        {result_html}
        <div class="box"><a href="/keys">← Danh sách key</a> | <a href="/my">← Trang cá nhân</a></div>"""
        return page("Tạo key", body)

    # ---------------- API MANAGER ----------------

    @app.route("/api")
    @require_login
    def api_page(me):
        if me["role"] != "admin":
            return page("API", nav(me) + '<div class="box">Chỉ admin.</div>')
        items = []
        if apikey:
            try:
                items = apikey.list_api_keys()
            except Exception:
                pass
        trs = ""
        for it in items:
            trs += f"""<tr>
              <td>{esc(it['name'])}</td>
              <td><code class="key">{esc(it['keyPreview'])}</code></td>
              <td>{esc(it['scopesText'])}</td>
              <td>{it['usageCount']}</td>
              <td class="{'on' if it['active'] else 'off'}">{'ON' if it['active'] else 'OFF'}</td>
              <td>
                <form method="POST" action="/api/toggle" style="display:inline">
                  <input type="hidden" name="key" value="{esc(it['key'])}">
                  <button class="neutral" type="submit">Đổi</button>
                </form>
                <form method="POST" action="/api/delete" style="display:inline">
                  <input type="hidden" name="key" value="{esc(it['key'])}">
                  <button class="danger" type="submit">Xóa</button>
                </form>
              </td>
            </tr>"""
        body = nav(me) + f"""
        <div class="box"><h1>QUẢN LÝ API KEY</h1>
        <form method="POST" action="/api/create">
            <div class="row">
              <input name="name" placeholder="tên client">
              <input name="scopes" value="verify,info" placeholder="quyền">
              <input name="rate_limit" value="60" placeholder="rate/phút">
            </div>
            <button type="submit">Tạo API Key</button>
        </form>
        </div>
        <div class="box">
        <table>
          <tr><th>Tên</th><th>Preview</th><th>Quyền</th><th>Dùng</th><th>Trạng thái</th><th>Hành động</th></tr>
          {trs or '<tr><td colspan="6" class="muted">Chưa có API key.</td></tr>'}
        </table>
        </div>
        <div class="box">
        <h2>Endpoint API</h2>
        <table>
          <tr><th>Method</th><th>Path</th><th>Mô tả</th></tr>
          <tr><td>POST</td><td>/api/verify</td><td>Xác thực key + device</td></tr>
          <tr><td>POST</td><td>/api/info</td><td>Thông tin key</td></tr>
          <tr><td>GET</td><td>/api/health</td><td>Trạng thái service</td></tr>
          <tr><td>GET</td><td>/api/stats</td><td>Thống kê (cần token)</td></tr>
        </table>
        <div class="muted" style="margin-top:8px">
          Gửi header <code>X-API-Key: ks_...</code> khi gọi API.
        </div>
        </div>"""
        return page("API", body)

    @app.route("/api/create", methods=["POST"])
    @require_login
    def api_create(me):
        if me["role"] != "admin" or not apikey:
            return redirect("/api")
        try:
            raw = apikey.create_api_key(
                request.form.get("name", "client"),
                request.form.get("scopes", "verify,info").split(","),
                "client",
                parse_int(request.form.get("rate_limit", 60), 60))
        except Exception:
            return redirect("/api")
        body = nav(me) + f"""
        <div class="box">
        <h1>✅ API KEY ĐÃ TẠO</h1>
        <div class="key"><code>{esc(raw)}</code></div>
        <div class="muted">Lưu lại ngay, không hiển thị lại.</div>
        </div>
        <div class="box"><a href="/api">← Quay lại</a></div>"""
        return page("API Key", body)

    @app.route("/api/toggle", methods=["POST"])
    @require_login
    def api_toggle(me):
        if me["role"] != "admin" or not apikey:
            return redirect("/api")
        try:
            apikey.toggle_api_key(request.form.get("key", ""))
        except Exception:
            pass
        return redirect("/api")

    @app.route("/api/delete", methods=["POST"])
    @require_login
    def api_delete(me):
        if me["role"] != "admin" or not apikey:
            return redirect("/api")
        try:
            apikey.delete_api_key(request.form.get("key", ""))
        except Exception:
            pass
        return redirect("/api")

    # ---------------- API JSON ----------------

    @app.route("/api/health")
    def api_health():
        return jsonify({
            "ok": True, "service": "key-server",
            "uptime": now_ms() - _bot_state["started_at"],
            "port": os.environ.get("PORT", "10000"),
        })

    @app.route("/api/verify", methods=["POST"])
    def api_verify():
        data = request.get_json(force=True, silent=True) or {}
        key = (data.get("key") or "").strip()
        device = (data.get("device_id") or "").strip()
        if not key or not device:
            return jsonify({"ok": False, "error": "missing_params"}), 400
        if not keymod:
            return jsonify({"ok": False, "error": "module_error"}), 500
        ip = request.headers.get("X-Forwarded-For",
                                  request.remote_addr or "").split(",")[0].strip()
        ua = request.headers.get("User-Agent", "unknown")
        result = keymod.verify_key(key, device, ip, ua)
        return jsonify(result), (200 if result.get("ok") else 403)

    @app.route("/api/info", methods=["POST"])
    def api_info():
        data = request.get_json(force=True, silent=True) or {}
        key = (data.get("key") or "").strip()
        if not key:
            return jsonify({"ok": False, "error": "missing_params"}), 400
        if not keymod:
            return jsonify({"ok": False, "error": "module_error"}), 500
        info = keymod.get_key_info(key)
        if not info:
            return jsonify({"ok": False, "error": "key_not_found"}), 404
        return jsonify({"ok": True, **info})

    # ---------------- WEBHOOK ----------------

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

    # ---------------- INDEX ----------------

    @app.route("/")
    def index():
        me = current_user()
        return redirect("/my" if me else "/login")

    @app.route("/ping")
    def ping():
        return "pong"

    @app.route("/health")
    def health():
        return jsonify({
            "ok": True,
            "bot": "running" if BOT_TOKEN else "no-token",
            "uptime": now_ms() - _bot_state["started_at"],
            "updates": _bot_state["updates_handled"],
            "commands": _bot_state["commands_handled"],
            "errors": _bot_state["errors"],
            "port": os.environ.get("PORT", "10000"),
        })

    # ---------------- RUN ----------------

    port = int(os.environ.get("PORT", 10000))
    host = "0.0.0.0"
    print(f"[HTTP] Flask chạy trên {host}:{port}")
    print("[HTTP] /login /register /my /keys /create /api")
    app.run(host=host, port=port, threaded=True,
            use_reloader=False, debug=False)

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
    return False

def main():
    ensure_dir(DATA_DIR)
    print(f"[BOT] Python: {sys.version.split()[0]}")
    print(f"[BOT] PORT: {os.environ.get('PORT', '10000')}")
    print(f"[BOT] DATA_DIR: {DATA_DIR}")
    print(f"[BOT] BOT_TOKEN: {'SET' if BOT_TOKEN else 'MISSING'}")

    http_thread = threading.Thread(target=run_http_server,
                                    daemon=True, name="http-server")
    http_thread.start()
    print("[BOT] Đã khởi động HTTP server thread")
    time.sleep(1)

    if not BOT_TOKEN:
        print("[BOT] Không có BOT_TOKEN, chỉ chạy HTTP server.")
        while True:
            time.sleep(3600)

    wait_for_token()
    while not check_bot():
        print("[BOT] Token chưa hợp lệ. Thử lại sau 30s...")
        time.sleep(30)

    start_workers()
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
