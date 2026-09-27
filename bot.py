# ============================================================
# FILE: bot.py
# MÔ TẢ: Bot Telegram + Web Server Flask V2 đầy đủ
# ============================================================

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
from functools import wraps

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

    def fetchone(*a, **k): return None
    def fetchall(*a, **k): return []
    def execute(*a, **k): return None
    def insert(*a, **k): return None
    def update(*a, **k): return 0
    def delete(*a, **k): return 0

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
BROADCAST_DELAY = float(os.environ.get("BROADCAST_DELAY", "0.05"))

SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "true").lower() == "true"
SESSION_TTL_MS = int(os.environ.get("SESSION_TTL_MS", str(7 * 86400000)))
MAX_LOGIN_ATTEMPTS = int(os.environ.get("MAX_LOGIN_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MS = int(os.environ.get("LOGIN_LOCKOUT_MS", "900000"))
RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "60"))
CSRF_ENABLED = os.environ.get("CSRF_ENABLED", "true").lower() == "true"

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
# RATE LIMIT (IN-MEMORY)
# ============================================================

_rl_store = {}
_rl_lock = threading.Lock()

def rate_limit(key, limit=RATE_LIMIT_PER_MIN, window=60):
    now = time.time()
    with _rl_lock:
        bucket = _rl_store.setdefault(key, [])
        bucket[:] = [t for t in bucket if now - t < window]
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

def _client_ip(req):
    fwd = req.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return req.remote_addr or "0.0.0.0"

# ============================================================
# CSRF
# ============================================================

def _csrf_secret():
    s = os.environ.get("CSRF_SECRET")
    if not s:
        s = hashlib.sha256((os.environ.get("BOT_TOKEN", "x") + "csrf").encode()).hexdigest()
    return s

def make_csrf(uid, ts=None):
    ts = ts or int(time.time())
    raw = f"{uid}:{ts}"
    sig = hashlib.sha256((_csrf_secret() + raw).encode()).hexdigest()[:32]
    return f"{ts}.{sig}"

def check_csrf(uid, token):
    if not token or "." not in token:
        return False
    ts_s, sig = token.split(".", 1)
    try:
        ts = int(ts_s)
    except ValueError:
        return False
    if time.time() - ts > 7200:
        return False
    expect = hashlib.sha256((_csrf_secret() + f"{uid}:{ts}").encode()).hexdigest()[:32]
    return secrets.compare_digest(expect, sig)

# ============================================================
# TẠO TÀI KHOẢN ADMIN MẶC ĐỊNH
# ============================================================

def ensure_admin_account():
    accounts = [
        ("baohuy", "baohuy"),
    ]
    for username, password in accounts:
        try:
            existing = fetchone(
                "SELECT uid FROM accounts WHERE username = ?", (username,))
            if existing:
                print(f"[BOT] Tài khoản {username} đã tồn tại")
                continue
            uid = secrets.token_hex(8)
            salt = secrets.token_hex(16)
            pw_hash = f"{salt}${hashlib.sha256((salt + password).encode()).hexdigest()}"
            execute(
                "INSERT INTO accounts "
                "(uid, username, password_hash, role, active, created_at) "
                "VALUES (?, ?, ?, 'admin', 1, ?)",
                (uid, username, pw_hash, now_ms()))
            print(f"[BOT] Đã tạo tài khoản admin: {username} / {password}")
        except Exception as e:
            print(f"[BOT] ensure_admin_account lỗi ({username}): {e}")

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
    return bool(tg_call("editMessageText", payload))

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
# USER / KEY
# ============================================================

def is_admin(user_id):
    return str(user_id) in ADMIN_IDS

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
# BOT HANDLERS
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
/stats /health /broadcast
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
        role = "admin" if is_admin(user_id) else "user"
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
    if cmd == "/myinfo":
        k = get_key_by_user(user_id)
        role = "admin" if is_admin(user_id) else "user"
        send_message(chat_id,
            f"ID: <code>{esc(user_id)}</code>\n"
            f"Vai trò: {role}\n"
            f"Key: <code>{esc(k or 'chưa có')}</code>")
        return
    if cmd == "/info" and len(parts) >= 2:
        info = keymod.get_key_info(parts[1]) if keymod else None
        if not info:
            send_message(chat_id, "Key không tồn tại.")
            return
        send_message(chat_id,
            f"Key: <code>{esc(info['key'])}</code>\n"
            f"Chủ: {esc(info.get('owner','-'))}\n"
            f"Còn: {info['daysLeft']} ngày\n"
            f"TB: {info['devicesUsed']}/{info['maxDevices']}")
        return
    if cmd == "/days" and len(parts) >= 2:
        info = keymod.get_key_info(parts[1]) if keymod else None
        if not info:
            send_message(chat_id, "Key không tồn tại.")
            return
        send_message(chat_id, f"Còn {info['daysLeft']} ngày.")
        return
    if cmd == "/verify" and len(parts) >= 3:
        if not keymod:
            send_message(chat_id, "Module key lỗi.")
            return
        result = keymod.verify_key(parts[1], parts[2], "tg", "telegram")
        if result.get("ok"):
            send_message(chat_id, "✅ Key hợp lệ.")
        else:
            send_message(chat_id, f"❌ {result.get('error', 'không hợp lệ')}")
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
    if cmd == "/broadcast" and is_admin(user_id):
        msg = text[len("/broadcast"):].strip()
        if not msg:
            send_message(chat_id, "Cú pháp: /broadcast &lt;nội dung&gt;")
            return
        users = list_telegram_users()
        sent, fail = 0, 0
        for uid in users:
            if send_message(uid, msg):
                sent += 1
            else:
                fail += 1
            time.sleep(BROADCAST_DELAY)
        send_message(chat_id, f"Đã gửi: {sent} | Lỗi: {fail}")
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
    backoff = 3
    print("[BOT] Bắt đầu polling...")
    while True:
        try:
            res = tg_call("getUpdates", {
                "offset": offset, "timeout": 30,
                "allowed_updates": ["message", "callback_query"],
            }, timeout=40)
            if not res or not res.get("ok"):
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue
            backoff = 3
            for upd in res.get("result", []):
                offset = upd["update_id"] + 1
                handle_update(upd)
        except Exception as e:
            print(f"[BOT] polling lỗi: {e}")
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)

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
# CSS V2 - DARK MODERN UI
# ============================================================

CSS_V2 = """
<style>
:root{
  --bg:#0a0e14; --bg2:#0f141b; --panel:#141a22; --panel2:#1a212b;
  --border:#232c38; --border2:#2d3946;
  --fg:#c9d1d9; --fg2:#8b949e; --fg3:#6a737d;
  --accent:#58a6ff; --accent2:#1f6feb;
  --ok:#3fb950; --warn:#d29922; --err:#f85149; --info:#79c0ff;
  --radius:8px; --radius2:12px;
  --shadow:0 4px 16px rgba(0,0,0,.4);
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{
  background:linear-gradient(180deg,#0a0e14 0%,#0d1117 100%);
  color:var(--fg);
  font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  font-size:14px;line-height:1.5;
  -webkit-font-smoothing:antialiased;
  min-height:100vh;
}
h1{font-size:20px;color:var(--accent);margin:0 0 6px}
h2{font-size:16px;color:var(--accent);margin:0 0 10px;font-weight:600}
h3{font-size:14px;color:var(--info);margin:0 0 6px}
a{color:var(--accent);text-decoration:none;transition:color .15s}
a:hover{color:var(--info)}
.topnav{
  position:sticky;top:0;z-index:50;
  display:flex;align-items:center;gap:8px;flex-wrap:wrap;
  padding:10px 14px;
  background:rgba(15,20,27,.95);
  backdrop-filter:blur(8px);
  border-bottom:1px solid var(--border);
  margin:-12px -12px 14px;
}
.topnav .brand{
  font-weight:700;color:var(--accent);letter-spacing:.5px;
  padding:4px 8px;border-radius:6px;background:var(--panel);
}
.topnav .spacer{flex:1}
.topnav a.navlink{
  padding:5px 10px;border-radius:6px;background:var(--panel2);
  color:var(--fg2);font-size:12px;transition:all .15s;
}
.topnav a.navlink:hover{background:var(--border2);color:var(--fg)}
.topnav a.navlink.active{background:var(--accent2);color:#fff}
.tag{
  display:inline-flex;align-items:center;gap:4px;
  padding:3px 8px;border-radius:20px;
  font-size:11px;font-weight:600;
  background:var(--panel2);color:var(--fg2);
}
.tag.admin{background:rgba(240,136,62,.15);color:#f0883e;border:1px solid rgba(240,136,62,.3)}
.tag.user{background:rgba(63,185,80,.15);color:var(--ok);border:1px solid rgba(63,185,80,.3)}
.tag.on{background:rgba(63,185,80,.15);color:var(--ok)}
.tag.off{background:rgba(248,81,73,.15);color:var(--err)}
.panel{
  background:var(--panel);
  border:1px solid var(--border);
  border-radius:var(--radius2);
  padding:16px;margin:0 0 14px;
  box-shadow:var(--shadow);
}
.panel.tight{padding:12px}
input,button,select,textarea{
  width:100%;
  background:var(--bg2);color:var(--fg);
  border:1px solid var(--border2);
  padding:10px 12px;border-radius:var(--radius);
  font-family:inherit;font-size:13px;
  transition:border-color .15s,box-shadow .15s;
}
input:focus,textarea:focus,select:focus{
  outline:none;border-color:var(--accent2);
  box-shadow:0 0 0 3px rgba(31,111,235,.2);
}
input::placeholder{color:var(--fg3)}
button{
  background:var(--accent2);color:#fff;font-weight:600;
  cursor:pointer;border:none;padding:10px 14px;
  letter-spacing:.3px;
}
button:hover{background:#388bfd}
button:active{transform:translateY(1px)}
button.danger{background:#b62324}
button.danger:hover{background:var(--err)}
button.neutral{background:var(--panel2);color:var(--fg)}
button.neutral:hover{background:var(--border2)}
button.ghost{background:transparent;border:1px solid var(--border2);color:var(--fg2)}
button.ghost:hover{border-color:var(--accent);color:var(--accent)}
button.small{padding:6px 10px;font-size:12px;width:auto}
.grid{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(160px,1fr))}
.grid-2{display:grid;gap:10px;grid-template-columns:1fr 1fr}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:flex-start}
.row > *{flex:1;min-width:120px}
.row.tight > *{min-width:0}
.stat{
  background:var(--bg2);border:1px solid var(--border);
  padding:12px;border-radius:var(--radius);
  transition:border-color .15s;
}
.stat:hover{border-color:var(--border2)}
.stat .label{color:var(--fg2);font-size:11px;text-transform:uppercase;letter-spacing:.5px}
.stat .value{color:var(--accent);font-size:22px;font-weight:700;margin-top:4px;display:block}
.stat.ok .value{color:var(--ok)}
.stat.warn .value{color:var(--warn)}
.stat.err .value{color:var(--err)}
table{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}
th,td{border-bottom:1px solid var(--border);padding:9px 8px;text-align:left;vertical-align:top}
th{background:var(--bg2);color:var(--accent);font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.5px}
tr:hover td{background:rgba(88,166,255,.04)}
td code{background:var(--bg2);padding:2px 6px;border-radius:4px;color:var(--ok);word-break:break-all;font-size:11px}
.codeblock{
  background:#010409;border:1px solid var(--border);
  border-radius:var(--radius);padding:12px;
  font-family:inherit;font-size:12px;
  color:var(--ok);word-break:break-all;
  overflow-x:auto;position:relative;
}
.codeblock::before{
  content:attr(data-label);
  position:absolute;top:6px;right:8px;
  color:var(--fg3);font-size:10px;text-transform:uppercase;
}
.alert{
  padding:10px 12px;border-radius:var(--radius);
  font-size:12px;margin-top:8px;
  border-left:3px solid;
}
.alert.err{background:rgba(248,81,73,.08);color:var(--err);border-color:var(--err)}
.alert.ok{background:rgba(63,185,80,.08);color:var(--ok);border-color:var(--ok)}
.alert.warn{background:rgba(210,153,34,.08);color:var(--warn);border-color:var(--warn)}
.alert.info{background:rgba(121,192,255,.08);color:var(--info);border-color:var(--info)}
.wrap{max-width:440px;margin:40px auto;padding:0 12px}
.wrap.wide{max-width:1100px}
.container{max-width:1100px;margin:0 auto;padding:12px}
.muted{color:var(--fg2);font-size:12px}
.tiny{font-size:11px;color:var(--fg3)}
.center{text-align:center}
.mt{margin-top:12px}.mb{margin-bottom:12px}
.toast{
  position:fixed;bottom:20px;right:20px;z-index:100;
  background:var(--panel);border:1px solid var(--border2);
  padding:12px 16px;border-radius:var(--radius);
  box-shadow:var(--shadow);
  animation:slideIn .3s ease-out;
  max-width:340px;
}
.toast.ok{border-left:3px solid var(--ok)}
.toast.err{border-left:3px solid var(--err)}
@keyframes slideIn{from{transform:translateX(120%)}to{transform:translateX(0)}}
@media(max-width:640px){
  .topnav{padding:8px}
  .topnav a.navlink{padding:4px 8px;font-size:11px}
  .panel{padding:12px}
  .stat .value{font-size:18px}
  h1{font-size:17px}
  .wrap{margin:20px auto}
  .grid-2{grid-template-columns:1fr}
}
</style>
"""

# ============================================================
# HTML HELPERS
# ============================================================

def _esc(t):
    if t is None: return ""
    return html.escape(str(t), quote=False)

def _page(title, body):
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0a0e14">
<meta name="robots" content="noindex,nofollow">
<title>{_esc(title)} · KEY SERVER</title>
{CSS_V2}
</head>
<body>
<div class="container">{body}</div>
</body>
</html>"""

def _toast(msg, kind="ok"):
    if not msg: return ""
    return f'<div class="toast {kind}">{_esc(msg)}</div>'

# ============================================================
# FLASK WEB SERVER V2
# ============================================================

def run_http_server():
    try:
        from flask import (Flask, jsonify, request, make_response,
                           redirect, abort)
    except ImportError:
        print("[HTTP] Flask không có, không mở port")
        return

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024
    app.config["JSON_SORT_KEYS"] = False

    # ---------- AUTH HELPERS ----------

    def hash_password(password, salt=None):
        if not salt:
            salt = secrets.token_hex(16)
        h = hashlib.sha256((salt + password).encode()).hexdigest()
        return f"{salt}${h}"

    def check_password(password, stored):
        try:
            salt, h = stored.split("$", 1)
            return secrets.compare_digest(
                hashlib.sha256((salt + password).encode()).hexdigest(), h)
        except Exception:
            return False

    def get_account_by_uid(uid):
        try: return fetchone("SELECT * FROM accounts WHERE uid = ?", (uid,))
        except Exception: return None

    def get_account_by_username(u):
        try: return fetchone("SELECT * FROM accounts WHERE username = ?", (u,))
        except Exception: return None

    def create_token(uid):
        token = secrets.token_urlsafe(32)
        try:
            execute("INSERT OR REPLACE INTO sessions "
                    "(token, uid, created_at, expires_at) VALUES (?, ?, ?, ?)",
                    (token, uid, now_ms(), now_ms() + SESSION_TTL_MS))
        except Exception: pass
        return token

    def uid_from_token(token):
        if not token: return None
        try:
            row = fetchone(
                "SELECT uid FROM sessions WHERE token = ? AND expires_at > ?",
                (token, now_ms()))
            return row["uid"] if row else None
        except Exception: return None

    def destroy_token(token):
        try: execute("DELETE FROM sessions WHERE token = ?", (token,))
        except Exception: pass

    def current_user():
        uid = uid_from_token(request.cookies.get("session"))
        if not uid: return None
        rec = get_account_by_uid(uid)
        if not rec or not rec.get("active"): return None
        return {
            "uid": uid, "username": rec["username"],
            "role": rec["role"] or "user",
            "csrf": make_csrf(uid),
        }

    def login_required(f):
        @wraps(f)
        def w(*a, **k):
            me = current_user()
            if not me:
                return redirect("/login?next=" + _esc(request.path))
            return f(me, *a, **k)
        return w

    def admin_required(f):
        @wraps(f)
        def w(*a, **k):
            me = current_user()
            if not me:
                return redirect("/login")
            if me["role"] != "admin":
                abort(403)
            return f(me, *a, **k)
        return w

    def verify_csrf():
        if not CSRF_ENABLED: return True
        me = current_user()
        if not me: return False
        return check_csrf(me["uid"], request.form.get("csrf", ""))

    # ---------- HOOKS ----------

    @app.before_request
    def _rl_global():
        ip = _client_ip(request)
        if request.path.startswith(("/api/verify", "/api/info", "/api/health")):
            return None
        if not rate_limit(f"ip:{ip}", limit=120, window=60):
            return jsonify({"ok": False, "error": "rate_limited"}), 429
        return None

    @app.after_request
    def _sec(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
        return resp

    # ---------- ERROR HANDLERS ----------

    @app.errorhandler(403)
    def _403(e):
        return _page("403", """
        <div class="wrap"><div class="panel center">
        <h1>403</h1><p class="muted">Không có quyền truy cập.</p>
        <div class="mt"><a href="/my"><button>← Về trang chủ</button></a></div>
        </div></div>"""), 403

    @app.errorhandler(404)
    def _404(e):
        return _page("404", """
        <div class="wrap"><div class="panel center">
        <h1>404</h1><p class="muted">Không tìm thấy trang.</p>
        <div class="mt"><a href="/my"><button>← Về trang chủ</button></a></div>
        </div></div>"""), 404

    @app.errorhandler(429)
    def _429(e):
        return jsonify({"ok": False, "error": "rate_limited"}), 429

    @app.errorhandler(500)
    def _500(e):
        return _page("500", """
        <div class="wrap"><div class="panel center">
        <h1>500</h1><p class="muted">Lỗi máy chủ.</p>
        </div></div>"""), 500

    # ---------- NAV ----------

    def nav(me=None, active=""):
        def cls(name):
            return "navlink" + (" active" if active == name else "")
        if me:
            role_cls = "admin" if me["role"] == "admin" else "user"
            links = (
                f'<a class="{cls("my")}" href="/my">Cá nhân</a>'
                f'<a class="{cls("keys")}" href="/keys">Keys</a>'
                f'<a class="{cls("create")}" href="/create">Tạo key</a>'
            )
            if me["role"] == "admin":
                links += (
                    f'<a class="{cls("api")}" href="/api">API</a>'
                    f'<a class="{cls("admin")}" href="/admin">Admin</a>'
                )
            tag = (f'<span class="tag {role_cls}">{_esc(me["username"])}</span>'
                   f'<a class="{cls("logout")}" href="/logout">Thoát</a>')
            return (f'<div class="topnav"><span class="brand">🔑 KEY SERVER</span>'
                    f'{links}<span class="spacer"></span>{tag}</div>')
        return (f'<div class="topnav"><span class="brand">🔑 KEY SERVER</span>'
                f'<span class="spacer"></span>'
                f'<a class="{cls("login")}" href="/login">Đăng nhập</a>'
                f'<a class="{cls("register")}" href="/register">Đăng ký</a></div>')

    # ============================================================
    # AUTH ROUTES
    # ============================================================

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = ""
        if request.method == "POST":
            if not rate_limit(f"login:{_client_ip(request)}", 5, 60):
                error = "Quá nhiều lần thử. Vui lòng chờ."
            else:
                u = request.form.get("username", "").strip()
                p = request.form.get("password", "")
                rec = get_account_by_username(u)
                if not rec or not check_password(p, rec["password_hash"] or ""):
                    error = "Sai tài khoản hoặc mật khẩu."
                elif not rec.get("active"):
                    error = "Tài khoản đã bị khóa."
                else:
                    token = create_token(rec["uid"])
                    nxt = request.args.get("next") or "/my"
                    if not nxt.startswith("/"): nxt = "/my"
                    resp = make_response(redirect(nxt))
                    resp.set_cookie("session", token,
                                    httponly=True, samesite="Lax",
                                    secure=SECURE_COOKIES, max_age=604800)
                    return resp
        body = nav() + f"""
        <div class="wrap"><div class="panel">
        <h1>🔑 ĐĂNG NHẬP</h1>
        <p class="muted mb">Nhập thông tin tài khoản để tiếp tục.</p>
        <form method="POST" autocomplete="on">
            <input name="username" placeholder="tài khoản" autocomplete="username" required>
            <input name="password" type="password" placeholder="mật khẩu" autocomplete="current-password" required>
            {f'<div class="alert err">{_esc(error)}</div>' if error else ''}
            <button type="submit" class="mt">Đăng nhập</button>
        </form>
        <div class="center mt muted">
            Chưa có tài khoản? <a href="/register">Đăng ký ngay</a>
        </div>
        </div></div>"""
        return _page("Đăng nhập", body)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        error = ""
        if request.method == "POST":
            if not rate_limit(f"reg:{_client_ip(request)}", 3, 300):
                error = "Quá nhiều yêu cầu đăng ký."
            else:
                u = request.form.get("username", "").strip()
                p = request.form.get("password", "")
                p2 = request.form.get("password2", "")
                if len(u) < 3 or not u.replace("_", "").isalnum():
                    error = "Tài khoản ≥3 ký tự, chỉ chữ/số/gạch dưới."
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
                        execute("INSERT INTO accounts "
                                "(uid, username, password_hash, role, active, created_at) "
                                "VALUES (?, ?, ?, 'user', 1, ?)",
                                (uid, u, pw_hash, now_ms()))
                        token = create_token(uid)
                        resp = make_response(redirect("/my"))
                        resp.set_cookie("session", token,
                                        httponly=True, samesite="Lax",
                                        secure=SECURE_COOKIES, max_age=604800)
                        return resp
                    except Exception as e:
                        error = f"Lỗi: {e}"
        body = nav() + f"""
        <div class="wrap"><div class="panel">
        <h1>🔑 ĐĂNG KÝ</h1>
        <p class="muted mb">Tạo tài khoản mới để nhận key.</p>
        <form method="POST">
            <input name="username" placeholder="tài khoản (≥3)" required>
            <input name="password" type="password" placeholder="mật khẩu (≥6)" required>
            <input name="password2" type="password" placeholder="nhập lại mật khẩu" required>
            {f'<div class="alert err">{_esc(error)}</div>' if error else ''}
            <button type="submit" class="mt">Đăng ký</button>
        </form>
        <div class="center mt muted">
            Đã có tài khoản? <a href="/login">Đăng nhập</a>
        </div>
        </div></div>"""
        return _page("Đăng ký", body)

    @app.route("/logout")
    def logout():
        destroy_token(request.cookies.get("session"))
        resp = make_response(redirect("/login"))
        resp.set_cookie("session", "", max_age=0, secure=SECURE_COOKIES)
        return resp

    # ============================================================
    # MY PANEL
    # ============================================================

    @app.route("/my")
    @login_required
    def my_panel(me):
        rec = get_account_by_uid(me["uid"])
        my_key = rec.get("key") if rec else None
        key_html = ""
        if my_key and keymod:
            try:
                info = keymod.get_key_info(my_key)
                if info:
                    days_left = info.get("daysLeft", 0)
                    cls = "ok" if days_left > 7 else ("warn" if days_left > 0 else "err")
                    key_html = f"""
                    <div class="codeblock" data-label="KEY">{_esc(info['key'])}</div>
                    <div class="grid mt">
                      <div class="stat"><span class="label">Chủ</span>
                        <span class="value" style="font-size:14px">{_esc(info.get('owner','-'))}</span></div>
                      <div class="stat {cls}"><span class="label">Còn lại</span>
                        <span class="value">{days_left} ngày</span></div>
                      <div class="stat"><span class="label">Thiết bị</span>
                        <span class="value">{info.get('devicesUsed',0)}/{info.get('maxDevices',1)}</span></div>
                      <div class="stat"><span class="label">Hết hạn</span>
                        <span class="value" style="font-size:12px">{_esc(info.get('expiresAtText','-'))}</span></div>
                    </div>
                    <button class="neutral small mt" onclick="navigator.clipboard.writeText('{_esc(info['key'])}')">
                      📋 Copy key
                    </button>"""
            except Exception: pass
        if not key_html:
            key_html = f"""
            <div class="alert info">Bạn chưa có key nào.</div>
            <form method="POST" action="/my/getkey" class="mt">
                <input type="hidden" name="csrf" value="{me['csrf']}">
                <button type="submit">🎁 NHẬN KEY MIỄN PHÍ</button>
            </form>"""

        success = request.args.get("success", "")
        error = request.args.get("error", "")
        toast = _toast(success, "ok") if success else (_toast(error, "err") if error else "")
        body = nav(me, "my") + toast + f"""
        <div class="panel">
          <h1>👋 {_esc(me['username'])}</h1>
          <p class="muted">Vai trò: <span class="tag {me['role']}">{_esc(me['role'])}</span>
          · UID: <code>{_esc(me['uid'])}</code></p>
        </div>
        <div class="panel"><h2>🔑 KEY CỦA BẠN</h2>{key_html}</div>
        <div class="grid-2">
          <div class="panel"><h2>🔒 ĐỔI MẬT KHẨU</h2>
            <form method="POST" action="/my/changepw">
              <input type="hidden" name="csrf" value="{me['csrf']}">
              <input name="old_password" type="password" placeholder="mật khẩu cũ" required>
              <input name="new_password" type="password" placeholder="mật khẩu mới (≥6)" required>
              <button type="submit" class="mt">Đổi mật khẩu</button>
            </form>
          </div>
          <div class="panel"><h2>⚡ THAO TÁC NHANH</h2>
            <p class="muted mb">Truy cập nhanh các chức năng.</p>
            <div class="row tight">
              <a href="/keys"><button class="neutral small">📋 Keys</button></a>
              <a href="/create"><button class="neutral small">➕ Tạo key</button></a>
            </div>
            <form method="POST" action="/my/revoke" class="mt"
                  onsubmit="return confirm('Thu hồi key hiện tại?')">
              <input type="hidden" name="csrf" value="{me['csrf']}">
              <button type="submit" class="danger small">🗑 Thu hồi key</button>
            </form>
          </div>
        </div>"""
        return _page("Cá nhân", body)

    @app.route("/my/getkey", methods=["POST"])
    @login_required
    def my_getkey(me):
        if not verify_csrf():
            return redirect("/my?error=CSRF+không+hợp+lệ")
        if not keymod:
            return redirect("/my?error=Module+key+lỗi")
        rec = get_account_by_uid(me["uid"])
        if rec and rec.get("key"):
            return redirect("/my?error=Bạn+đã+có+key")
        try:
            k, exp, sig = keymod.create_key(
                DEFAULT_DAYS, rec["username"], DEFAULT_MAX_DEVICES,
                user_id=me["uid"])
            execute("UPDATE accounts SET key = ? WHERE uid = ?", (k, me["uid"]))
            notify_key_created(k, rec["username"], DEFAULT_DAYS, by=me["username"])
        except Exception:
            return redirect("/my?error=Lỗi+tạo+key")
        return redirect("/my?success=Đã+cấp+key+thành+công")

    @app.route("/my/revoke", methods=["POST"])
    @login_required
    def my_revoke(me):
        if not verify_csrf():
            return redirect("/my?error=CSRF")
        rec = get_account_by_uid(me["uid"])
        if rec and rec.get("key") and keymod:
            try:
                if hasattr(keymod, "revoke_key"):
                    keymod.revoke_key(rec["key"])
                else:
                    execute("UPDATE keys SET active = 0 WHERE key = ?", (rec["key"],))
                execute("UPDATE accounts SET key = NULL WHERE uid = ?", (me["uid"],))
            except Exception: pass
        return redirect("/my?success=Đã+thu+hồi+key")

    @app.route("/my/changepw", methods=["POST"])
    @login_required
    def my_changepw(me):
        if not verify_csrf():
            return redirect("/my?error=CSRF")
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

    # ============================================================
    # KEYS LIST
    # ============================================================

    @app.route("/keys")
    @login_required
    def keys_list(me):
        q = request.args.get("q", "").strip()
        status = request.args.get("status", "all")
        page = max(1, int(request.args.get("page", "1") or 1))
        per_page = 25
        offset = (page - 1) * per_page
        where, params = [], []
        if q:
            where.append("(key LIKE ? OR owner LIKE ?)")
            params += [f"%{q}%", f"%{q}%"]
        if status == "active":
            where.append("active = 1 AND expires_at > ?")
            params.append(now_ms())
        elif status == "expired":
            where.append("expires_at <= ?")
            params.append(now_ms())
        elif status == "inactive":
            where.append("active = 0")
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        try:
            total_row = fetchone(f"SELECT COUNT(*) AS c FROM keys {where_sql}", tuple(params))
            total = total_row["c"] if total_row else 0
            rows = fetchall(
                f"SELECT * FROM keys {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                tuple(params) + (per_page, offset))
        except Exception:
            total, rows = 0, []
        now = now_ms()
        trs = ""
        for r in rows:
            days_left = max(0, int((r["expires_at"] - now) / 86400000))
            is_active = r["active"] and days_left > 0
            cls = "on" if is_active else "off"
            st = "ON" if is_active else ("HẾT HẠN" if days_left == 0 else "OFF")
            trs += f"""<tr>
              <td><code>{_esc(r['key'][:20])}…</code></td>
              <td>{_esc(r['owner'])}</td>
              <td><span class="tag {cls}">{st}</span></td>
              <td>{days_left}d</td>
              <td class="tiny">{fmt_time(r['expires_at'])}</td>
            </tr>"""
        pages = max(1, (total + per_page - 1) // per_page)
        pager = ""
        if pages > 1:
            pager = '<div class="row tight mt">'
            for i in range(1, pages + 1):
                if abs(i - page) <= 2 or i == 1 or i == pages:
                    qs = f"?q={_esc(q)}&status={status}&page={i}"
                    btn_cls = "neutral" if i != page else ""
                    pager += f'<a href="/keys{qs}"><button class="{btn_cls} small">{i}</button></a>'
            pager += '</div>'
        body = nav(me, "keys") + f"""
        <div class="panel">
          <h1>📋 DANH SÁCH KEY <span class="muted">({total})</span></h1>
          <form method="GET" class="row tight mb">
            <input name="q" value="{_esc(q)}" placeholder="Tìm key hoặc chủ...">
            <select name="status">
              <option value="all" {"selected" if status=="all" else ""}>Tất cả</option>
              <option value="active" {"selected" if status=="active" else ""}>Hoạt động</option>
              <option value="expired" {"selected" if status=="expired" else ""}>Hết hạn</option>
              <option value="inactive" {"selected" if status=="inactive" else ""}>Đã tắt</option>
            </select>
            <button type="submit" class="small">🔍 Tìm</button>
          </form>
          <table>
            <tr><th>Key</th><th>Chủ</th><th>Trạng thái</th><th>Còn</th><th>Hết hạn</th></tr>
            {trs or '<tr><td colspan="5" class="muted center">Không có key nào.</td></tr>'}
          </table>
          {pager}
        </div>"""
        return _page("Keys", body)

    # ============================================================
    # CREATE KEY
    # ============================================================

    @app.route("/create", methods=["GET", "POST"])
    @login_required
    def create_page(me):
        result_html = ""
        error = ""
        if request.method == "POST":
            if not verify_csrf():
                error = "CSRF không hợp lệ."
            else:
                days = parse_int(request.form.get("days", 30), 30)
                owner = request.form.get("owner", "").strip() or me["username"]
                max_dev = parse_int(request.form.get("max_devices", 1), 1)
                if days <= 0 or days > 3650:
                    error = "Số ngày 1–3650."
                elif max_dev <= 0 or max_dev > 1000:
                    error = "Max thiết bị 1–1000."
                elif not keymod:
                    error = "Module key lỗi."
                else:
                    try:
                        k, exp, sig = keymod.create_key(
                            days, owner, max_dev, created_by=me["username"])
                        notify_key_created(k, owner, days, by=me["username"])
                        result_html = f"""
                        <div class="panel">
                          <h2>✅ KEY ĐÃ TẠO</h2>
                          <div class="codeblock" data-label="KEY">{_esc(k)}</div>
                          <div class="grid mt">
                            <div class="stat"><span class="label">Chủ</span>
                              <span class="value" style="font-size:14px">{_esc(owner)}</span></div>
                            <div class="stat ok"><span class="label">Hạn</span>
                              <span class="value">{days} ngày</span></div>
                            <div class="stat"><span class="label">Hết hạn</span>
                              <span class="value" style="font-size:12px">{_esc(fmt_time(exp))}</span></div>
                            <div class="stat"><span class="label">Max TB</span>
                              <span class="value">{max_dev}</span></div>
                          </div>
                          <button class="neutral small mt" onclick="navigator.clipboard.writeText('{_esc(k)}')">
                            📋 Copy key
                          </button>
                        </div>"""
                    except Exception as e:
                        error = f"Lỗi tạo key: {e}"
        body = nav(me, "create") + f"""
        <div class="panel">
          <h1>➕ TẠO KEY MỚI</h1>
          <p class="muted mb">Điền thông tin để cấp key cho người dùng.</p>
          <form method="POST">
            <input type="hidden" name="csrf" value="{me['csrf']}">
            <div class="row">
              <input name="days" value="30" type="number" min="1" max="3650" placeholder="số ngày">
              <input name="owner" value="{_esc(me['username'])}" placeholder="chủ sở hữu">
              <input name="max_devices" value="1" type="number" min="1" max="1000" placeholder="max thiết bị">
            </div>
            {f'<div class="alert err">{_esc(error)}</div>' if error else ''}
            <button type="submit" class="mt">🎫 Tạo key</button>
          </form>
        </div>
        {result_html}"""
        return _page("Tạo key", body)

    # ============================================================
    # ADMIN PANEL
    # ============================================================

    @app.route("/admin")
    @admin_required
    def admin_panel(me):
        try:
            stats = fetchone("""
                SELECT
                  (SELECT COUNT(*) FROM keys) AS total,
                  (SELECT COUNT(*) FROM keys WHERE active=1 AND expires_at > ?) AS active,
                  (SELECT COUNT(*) FROM devices) AS devices,
                  (SELECT COUNT(*) FROM accounts) AS accounts
            """, (now_ms(),)) or {}
        except Exception:
            stats = {}
        try:
            recent = fetchall("SELECT * FROM keys ORDER BY created_at DESC LIMIT 5")
        except Exception:
            recent = []
        recent_rows = ""
        for r in recent:
            recent_rows += f"""<tr>
              <td><code>{_esc(r['key'][:16])}…</code></td>
              <td>{_esc(r['owner'])}</td>
              <td class="tiny">{fmt_time(r['created_at'])}</td>
            </tr>"""
        body = nav(me, "admin") + f"""
        <div class="panel"><h1>🛡 BẢNG ĐIỀU KHIỂN ADMIN</h1></div>
        <div class="grid">
          <div class="stat"><span class="label">Tổng keys</span><span class="value">{stats.get('total',0)}</span></div>
          <div class="stat ok"><span class="label">Hoạt động</span><span class="value">{stats.get('active',0)}</span></div>
          <div class="stat"><span class="label">Thiết bị</span><span class="value">{stats.get('devices',0)}</span></div>
          <div class="stat"><span class="label">Tài khoản</span><span class="value">{stats.get('accounts',0)}</span></div>
        </div>
        <div class="panel"><h2>📌 KEY GẦN ĐÂY</h2>
          <table>
            <tr><th>Key</th><th>Chủ</th><th>Thời gian</th></tr>
            {recent_rows or '<tr><td colspan="3" class="muted center">Chưa có.</td></tr>'}
          </table>
        </div>
        <div class="panel"><h2>⚙ HÀNH ĐỘNG</h2>
          <div class="row tight">
            <a href="/api"><button class="neutral small">🔐 Quản lý API</button></a>
            <a href="/keys"><button class="neutral small">📋 Tất cả keys</button></a>
          </div>
        </div>"""
        return _page("Admin", body)

    # ============================================================
    # API MANAGER
    # ============================================================

    @app.route("/api")
    @admin_required
    def api_page(me):
        items = []
        if apikey:
            try: items = apikey.list_api_keys()
            except Exception: pass
        trs = ""
        for it in items:
            trs += f"""<tr>
              <td>{_esc(it['name'])}</td>
              <td><code>{_esc(it['keyPreview'])}</code></td>
              <td class="tiny">{_esc(it['scopesText'])}</td>
              <td>{it['usageCount']}</td>
              <td><span class="tag {'on' if it['active'] else 'off'}">{'ON' if it['active'] else 'OFF'}</span></td>
              <td>
                <form method="POST" action="/api/toggle" style="display:inline">
                  <input type="hidden" name="csrf" value="{me['csrf']}">
                  <input type="hidden" name="key" value="{_esc(it['key'])}">
                  <button class="neutral small" type="submit">Đổi</button>
                </form>
                <form method="POST" action="/api/delete" style="display:inline"
                      onsubmit="return confirm('Xóa API key này?')">
                  <input type="hidden" name="csrf" value="{me['csrf']}">
                  <input type="hidden" name="key" value="{_esc(it['key'])}">
                  <button class="danger small" type="submit">Xóa</button>
                </form>
              </td>
            </tr>"""
        body = nav(me, "api") + f"""
        <div class="panel">
          <h1>🔐 QUẢN LÝ API KEY</h1>
          <form method="POST" action="/api/create">
            <input type="hidden" name="csrf" value="{me['csrf']}">
            <div class="row">
              <input name="name" placeholder="tên client" required>
              <input name="scopes" value="verify,info" placeholder="quyền (csv)">
              <input name="rate_limit" value="60" type="number" placeholder="rate/phút">
            </div>
            <button type="submit" class="mt">➕ Tạo API Key</button>
          </form>
        </div>
        <div class="panel">
          <table>
            <tr><th>Tên</th><th>Preview</th><th>Quyền</th><th>Dùng</th><th>Trạng thái</th><th></th></tr>
            {trs or '<tr><td colspan="6" class="muted center">Chưa có API key.</td></tr>'}
          </table>
        </div>
        <div class="panel">
          <h2>📡 ENDPOINT CÔNG KHAI</h2>
          <table>
            <tr><th>Method</th><th>Path</th><th>Mô tả</th></tr>
            <tr><td>POST</td><td>/api/verify</td><td>Xác thực key + thiết bị</td></tr>
            <tr><td>POST</td><td>/api/info</td><td>Thông tin key</td></tr>
            <tr><td>GET</td><td>/api/health</td><td>Trạng thái dịch vụ</td></tr>
          </table>
        </div>"""
        return _page("API", body)

    @app.route("/api/create", methods=["POST"])
    @admin_required
    def api_create(me):
        if not verify_csrf() or not apikey:
            return redirect("/api")
        try:
            raw = apikey.create_api_key(
                request.form.get("name", "client"),
                request.form.get("scopes", "verify,info").split(","),
                "client",
                parse_int(request.form.get("rate_limit", 60), 60))
        except Exception:
            return redirect("/api")
        body = nav(me, "api") + f"""
        <div class="panel">
          <h1>✅ API KEY ĐÃ TẠO</h1>
          <div class="codeblock" data-label="API KEY">{_esc(raw)}</div>
          <div class="alert warn mt">Lưu lại ngay. Không hiển thị lại.</div>
          <button class="neutral small mt" onclick="navigator.clipboard.writeText('{_esc(raw)}')">
            📋 Copy
          </button>
        </div>
        <div class="panel"><a href="/api">← Quay lại</a></div>"""
        return _page("API Key", body)

    @app.route("/api/toggle", methods=["POST"])
    @admin_required
    def api_toggle(me):
        if not verify_csrf() or not apikey:
            return redirect("/api")
        try: apikey.toggle_api_key(request.form.get("key", ""))
        except Exception: pass
        return redirect("/api")

    @app.route("/api/delete", methods=["POST"])
    @admin_required
    def api_delete(me):
        if not verify_csrf() or not apikey:
            return redirect("/api")
        try: apikey.delete_api_key(request.form.get("key", ""))
        except Exception: pass
        return redirect("/api")

    # ============================================================
    # PUBLIC JSON API
    # ============================================================

    @app.route("/api/health")
    def api_health():
        return jsonify({
            "ok": True, "service": "key-server",
            "uptime": now_ms() - _bot_state["started_at"],
            "port": os.environ.get("PORT", "10000"),
            "version": "2.0",
        })

    @app.route("/api/verify", methods=["POST"])
    def api_verify():
        if not rate_limit(f"verify:{_client_ip(request)}", 30, 60):
            return jsonify({"ok": False, "error": "rate_limited"}), 429
        data = request.get_json(force=True, silent=True) or {}
        key = (data.get("key") or "").strip()
        device = (data.get("device_id") or "").strip()
        if not key or not device:
            return jsonify({"ok": False, "error": "missing_params"}), 400
        if not keymod:
            return jsonify({"ok": False, "error": "module_error"}), 500
        ip = _client_ip(request)
        ua = request.headers.get("User-Agent", "unknown")
        result = keymod.verify_key(key, device, ip, ua)
        return jsonify(result), (200 if result.get("ok") else 403)

    @app.route("/api/info", methods=["POST"])
    def api_info():
        if not rate_limit(f"info:{_client_ip(request)}", 60, 60):
            return jsonify({"ok": False, "error": "rate_limited"}), 429
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

    # ============================================================
    # WEBHOOK + INDEX
    # ============================================================

    @app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
    def webhook():
        try:
            data = request.get_json(force=True, silent=True) or {}
            handle_update(data)
        except Exception as e:
            print(f"[HTTP] webhook lỗi: {e}")
        return "OK", 200

    @app.route("/")
    def index():
        me = current_user()
        return redirect("/my" if me else "/login")

    @app.route("/ping")
    def ping(): return "pong"

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

    # ============================================================
    # RUN
    # ============================================================

    port = int(os.environ.get("PORT", 10000))
    host = "0.0.0.0"
    print(f"[HTTP] Flask chạy {host}:{port}")
    print("[HTTP] Routes: /login /register /my /keys /create /api /admin")
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
    ensure_admin_account()
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
