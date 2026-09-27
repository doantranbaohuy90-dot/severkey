# bot.py
# Máy chủ key đầy đủ: Web UI, API JSON, Telegram Bot
# FIX: Telegram chạy được trên Render, không lỗi

import os
import json
import time
import threading
import base64
from functools import wraps
from flask import (
    Flask, request, jsonify, render_template_string,
    make_response, redirect, url_for,
)
import requests

import key as keymod
import auth as authmod

app = Flask(__name__)

# ---------------- CAU HINH ----------------

BOT_TOKEN = os.environ.get("BOT_TOKEN", "6190734534:AAFE2Y1VlLBUv_W3EMwwQ3TkKmMSJWzrHJc")
ADMIN_ID = str(os.environ.get("ADMIN_ID", "5736655322"))
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "admin_token_mac_dinh")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Cho phep nhieu admin cach nhau dau phay
ADMIN_IDS = set(
    x.strip() for x in os.environ.get("ADMIN_IDS", ADMIN_ID).split(",") if x.strip()
)

DEFAULT_DAYS = keymod.DEFAULT_DAYS
DEFAULT_MAX_DEVICES = keymod.DEFAULT_MAX_DEVICES
AUTO_ISSUE_ENABLED = os.environ.get("AUTO_ISSUE_ENABLED", "true").lower() == "true"
AUTO_ISSUE_ONCE = os.environ.get("AUTO_ISSUE_ONCE", "true").lower() == "true"

CTV_FILE = os.path.join(keymod.DATA_DIR, "ctv.json")
USER_FILE = os.path.join(keymod.DATA_DIR, "users.json")

CTV_MAX_DAYS = int(os.environ.get("CTV_MAX_DAYS", "30"))
CTV_MAX_KEYS = int(os.environ.get("CTV_MAX_KEYS", "50"))

lock = threading.Lock()

# Trang thai webhook
WEBHOOK_INFO = {"registered": False, "url": None, "last_error": None}


# ---------------- TIEN ICH ----------------


def send_message(chat_id, text):
    # Gui tin nhan Telegram, tra ve True/False
    if not BOT_TOKEN:
        print("[TG] Thieu BOT_TOKEN")
        return False
    try:
        r = requests.post(
            f"{API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=15,
        )
        if r.status_code != 200:
            print(f"[TG] sendMessage loi {r.status_code}: {r.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"[TG] sendMessage exception: {e}")
        return False


def get_client_ip(req):
    fwd = req.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return req.remote_addr or "unknown"


# ---------------- CTV ----------------


def load_ctv():
    return keymod.read_json(CTV_FILE, {})


def save_ctv(c):
    keymod.write_json(CTV_FILE, c)


def load_users():
    return keymod.read_json(USER_FILE, {})


def save_users(u):
    keymod.write_json(USER_FILE, u)


def is_ctv(user_id):
    return str(user_id) in load_ctv()


def is_admin(user_id):
    return str(user_id) in ADMIN_IDS


def add_ctv(user_id, name=None, max_keys=None, max_days=None):
    ctv = load_ctv()
    ctv[str(user_id)] = {
        "name": name or f"ctv_{user_id}",
        "maxKeys": int(max_keys) if max_keys is not None else CTV_MAX_KEYS,
        "maxDays": int(max_days) if max_days is not None else CTV_MAX_DAYS,
        "keysCreated": ctv.get(str(user_id), {}).get("keysCreated", 0),
        "addedAt": keymod.now_ms(),
        "active": True,
    }
    save_ctv(ctv)
    keymod.append_log("ctv_add", {"user_id": str(user_id), "name": name})


def remove_ctv(user_id):
    ctv = load_ctv()
    if str(user_id) in ctv:
        del ctv[str(user_id)]
        save_ctv(ctv)
        keymod.append_log("ctv_remove", {"user_id": str(user_id)})
        return True
    return False


def toggle_ctv(user_id):
    ctv = load_ctv()
    uid = str(user_id)
    if uid not in ctv:
        return None
    ctv[uid]["active"] = not ctv[uid].get("active", True)
    save_ctv(ctv)
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


# ---------------- NGHIEP VU BO SUNG ----------------


def get_key_by_user(user_id):
    rec = load_users().get(str(user_id))
    return rec.get("key") if rec else None


def get_or_create_key_for_user(user_id, owner=None, days=None, max_devices=None,
                               created_by=None, account_uid=None, parent_key=None):
    if AUTO_ISSUE_ONCE:
        existing = get_key_by_user(user_id)
        if existing:
            kr = keymod.load_keys().get(existing)
            if kr and kr.get("active") and keymod.now_ms() < kr["expiresAt"]:
                return {"created": False, "key": existing, "record": kr}
    days = days if days is not None else DEFAULT_DAYS
    owner = owner or f"user_{user_id}"
    max_devices = max_devices if max_devices is not None else DEFAULT_MAX_DEVICES
    k, exp, sig = keymod.create_key(
        days, owner, max_devices,
        user_id=user_id, created_by=created_by,
        account_uid=account_uid, parent_key=parent_key,
    )
    users = load_users()
    users[str(user_id)] = {"key": k, "owner": owner, "createdAt": keymod.now_ms()}
    save_users(users)
    if account_uid:
        authmod.set_account_key(account_uid, k)
    if created_by:
        increment_ctv_count(created_by)
    return {"created": True, "key": k, "expiresAt": exp, "signature": sig,
            "record": keymod.load_keys()[k]}


# ---------------- AUTH ----------------


def current_user():
    token = request.cookies.get("session")
    s = authmod.get_session(token)
    if not s:
        return None
    rec = authmod.load_accounts().get(s["uid"])
    if not rec or not rec.get("active", True):
        return None
    return {"uid": s["uid"], "username": rec["username"], "role": rec.get("role", "user")}


def require_login(perm=None):
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            me = current_user()
            if not me:
                return redirect(url_for("login"))
            if perm and not authmod.has_permission(me["role"], perm):
                return make_response("Không có quyền.", 403)
            return f(*args, **kwargs)
        return wrapper
    return deco


def require_admin_token(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.headers.get("X-Admin-Token") != ADMIN_TOKEN:
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


# ---------------- HTML ----------------


BASE_CSS = """
<style>
  * { box-sizing: border-box; }
  body { background:#0d1117; color:#c9d1d9; font-family:monospace; margin:0; padding:12px; }
  h1,h2,h3 { color:#58a6ff; margin:8px 0; }
  h1 { font-size:20px; }
  h2 { font-size:15px; border-bottom:1px solid #30363d; padding-bottom:4px; margin-top:0; }
  .box { border:1px solid #30363d; padding:12px; margin:10px 0; border-radius:8px; background:#161b22; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:8px; }
  .stat { border:1px solid #30363d; padding:10px; border-radius:6px; background:#0d1117; font-size:12px; }
  .stat b { color:#58a6ff; font-size:18px; display:block; margin-top:4px; }
  table { width:100%; border-collapse:collapse; font-size:12px; }
  th,td { border:1px solid #30363d; padding:5px; text-align:left; word-break:break-all; }
  th { background:#21262d; color:#58a6ff; }
  tr:hover td { background:#1c2128; }
  input,button,select,textarea { background:#0d1117; color:#c9d1d9; border:1px solid #30363d; padding:6px; font-family:monospace; border-radius:4px; width:100%; margin:3px 0; font-size:12px; }
  button { background:#238636; cursor:pointer; color:#fff; }
  button:hover { background:#2ea043; }
  button.danger { background:#da3633; }
  button.danger:hover { background:#f85149; }
  button.neutral { background:#30363d; }
  button.neutral:hover { background:#484f58; }
  .on { color:#3fb950; } .off { color:#f85149; } .blk { color:#d29922; }
  .user { color:#a371f7; } .ctv { color:#f0883e; }
  a { color:#58a6ff; text-decoration:none; }
  a:hover { text-decoration:underline; }
  .err { color:#f85149; font-size:12px; min-height:14px; }
  .ok { color:#3fb950; font-size:12px; }
  .key { color:#3fb950; font-size:12px; word-break:break-all; }
  .nav { display:flex; gap:8px; flex-wrap:wrap; align-items:center; padding:8px 10px; background:#161b22; border:1px solid #30363d; border-radius:8px; margin-bottom:10px; font-size:13px; }
  .nav a { padding:5px 10px; border-radius:4px; background:#21262d; }
  .nav a:hover { background:#30363d; text-decoration:none; }
  .nav .brand { color:#58a6ff; font-weight:bold; }
  .tree { font-size:12px; line-height:1.6; white-space:pre; overflow-x:auto; padding:10px; background:#0d1117; border:1px solid #30363d; border-radius:6px; }
  .row { display:flex; gap:8px; align-items:flex-start; flex-wrap:wrap; }
  .row > * { flex:1; min-width:110px; }
  .tag { display:inline-block; padding:2px 6px; border-radius:4px; font-size:11px; background:#21262d; color:#8b949e; }
  .tag.admin { background:#3a2a00; color:#f0883e; }
  .tag.ctv { background:#2a1a3a; color:#a371f7; }
  .tag.user { background:#0d2818; color:#3fb950; }
  .scroll { max-height:520px; overflow-y:auto; }
  .empty { color:#8b949e; font-style:italic; padding:10px; text-align:center; }
  .status { padding:8px; border-radius:6px; margin:6px 0; font-size:12px; }
  .status.ok { background:#0d2818; color:#3fb950; border:1px solid #238636; }
  .status.err { background:#3a0a0a; color:#f85149; border:1px solid #da3633; }
</style>
"""


def nav_html(me, active=""):
    items = [
        ("/", "Dashboard", "dashboard"),
        ("/keys", "Keys", "keys"),
        ("/tree", "Cây Key", "tree"),
        ("/devices", "Thiết bị", "devices"),
        ("/blocks", "Block", "blocks"),
        ("/ctv", "CTV", "ctv"),
        ("/accounts", "Tài khoản", "accounts"),
        ("/logs", "Log", "logs"),
        ("/telegram", "Telegram", "telegram"),
    ]
    links = ""
    for url, label, name in items:
        style = ' style="background:#1f6feb;color:#fff"' if name == active else ""
        links += f'<a href="{url}"{style}>{label}</a>'
    if me:
        me_tag = f'<span class="tag {me["role"]}">{me["username"]} ({me["role"]})</span><a href="/logout">Thoát</a>'
    else:
        me_tag = '<a href="/login">Đăng nhập</a>'
    return f'<div class="nav"><span class="brand">🔑 KEY SERVER</span>{links}<span style="flex:1"></span>{me_tag}</div>'


def page(title, me, body, active=""):
    return f"""<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>{BASE_CSS}</head><body>
{nav_html(me, active)}
{body}
</body></html>"""


LOGIN_PAGE = """<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Đăng nhập</title>""" + BASE_CSS + """</head><body>
<div class="box" style="max-width:400px;margin:80px auto">
  <h1>🔑 ĐĂNG NHẬP</h1>
  <form method="POST" action="/login">
    <input name="username" placeholder="tài khoản" value="{{ prefill or '' }}">
    <input name="password" type="password" placeholder="mật khẩu">
    <div class="err">{{ error }}</div>
    <button type="submit">Đăng nhập</button>
  </form>
  <div style="text-align:center;margin-top:8px;font-size:12px">Chưa có tài khoản? <a href="/register">Đăng ký</a></div>
</div></body></html>"""


REGISTER_PAGE = """<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Đăng ký</title>""" + BASE_CSS + """</head><body>
<div class="box" style="max-width:400px;margin:80px auto">
  <h1>🔑 ĐĂNG KÝ</h1>
  <form method="POST" action="/register">
    <input name="username" placeholder="tài khoản (≥3 ký tự)">
    <input name="password" type="password" placeholder="mật khẩu (≥6 ký tự)">
    <input name="password2" type="password" placeholder="nhập lại mật khẩu">
    <div class="err">{{ error }}</div>
    <button type="submit">Đăng ký</button>
  </form>
  <div style="text-align:center;margin-top:8px;font-size:12px">Đã có tài khoản? <a href="/login">Đăng nhập</a></div>
</div></body></html>"""


# ---------------- ROUTE AUTH ----------------


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        uid, err = authmod.authenticate_account(u, p)
        if not uid:
            error = "Sai tài khoản hoặc mật khẩu."
        else:
            token = authmod.create_session(uid)
            resp = make_response(redirect(url_for("web_index")))
            resp.set_cookie("session", token, httponly=True, samesite="Lax",
                            max_age=authmod.SESSION_TTL)
            return resp
    return render_template_string(LOGIN_PAGE, error=error, prefill=authmod.DEFAULT_USER)


@app.route("/register", methods=["GET", "POST"])
def register():
    error = ""
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        p2 = request.form.get("password2", "")
        if p != p2:
            error = "Mật khẩu nhập lại không khớp."
        else:
            ok, result = authmod.register_account(u, p, ip=get_client_ip(request))
            if not ok:
                error = {
                    "missing_params": "Thiếu thông tin.",
                    "password_too_short": "Mật khẩu quá ngắn.",
                    "username_too_short": "Tài khoản quá ngắn.",
                    "username_exists": "Tài khoản đã tồn tại.",
                }.get(result, "Lỗi không xác định.")
            else:
                token = authmod.create_session(result)
                resp = make_response(redirect(url_for("my_panel")))
                resp.set_cookie("session", token, httponly=True, samesite="Lax",
                                max_age=authmod.SESSION_TTL)
                return resp
    return render_template_string(REGISTER_PAGE, error=error)


@app.route("/logout")
def logout():
    token = request.cookies.get("session")
    authmod.destroy_session(token)
    resp = make_response(redirect(url_for("login")))
    resp.set_cookie("session", "", max_age=0)
    return resp


# ---------------- DASHBOARD ----------------


def compute_stats():
    keys = keymod.load_keys()
    devices = keymod.load_devices()
    blocked = keymod.load_blocked()
    accounts = authmod.load_accounts()
    ctv = load_ctv()
    return {
        "totalKeys": len(keys),
        "activeKeys": sum(1 for v in keys.values() if v.get("active")),
        "expiredKeys": sum(1 for v in keys.values() if keymod.now_ms() > v.get("expiresAt", 0)),
        "totalDevices": sum(len(v) for v in devices.values()),
        "totalUsers": len(accounts),
        "totalCtv": len(ctv),
        "blockedKeys": len(blocked.get("keys", {})),
        "blockedDevices": len(blocked.get("devices", {})),
    }


DASHBOARD_BODY = """
<h1>DASHBOARD</h1>
<div class="grid">
  <div class="stat">Tổng key <b>{{ s.totalKeys }}</b></div>
  <div class="stat">Hoạt động <b class="on">{{ s.activeKeys }}</b></div>
  <div class="stat">Hết hạn <b class="off">{{ s.expiredKeys }}</b></div>
  <div class="stat">Thiết bị <b>{{ s.totalDevices }}</b></div>
  <div class="stat">Tài khoản <b>{{ s.totalUsers }}</b></div>
  <div class="stat">CTV <b class="ctv">{{ s.totalCtv }}</b></div>
  <div class="stat">Block key <b class="blk">{{ s.blockedKeys }}</b></div>
  <div class="stat">Block TB <b class="blk">{{ s.blockedDevices }}</b></div>
</div>

<div class="box">
  <h2>Tạo key mới</h2>
  <form method="POST" action="/web/create" class="row">
    <input name="days" value="30" placeholder="số ngày">
    <input name="owner" placeholder="chủ sở hữu">
    <input name="max_devices" value="1" placeholder="max thiết bị">
    <input name="parent" placeholder="key cha (tùy chọn)">
    <button type="submit">Tạo key</button>
  </form>
</div>

<div class="box">
  <h2>Cấp key theo user</h2>
  <form method="POST" action="/web/issue" class="row">
    <input name="user_id" placeholder="user_id">
    <input name="days" value="{{ default_days }}" placeholder="số ngày">
    <input name="owner" placeholder="chủ (tùy chọn)">
    <input name="max_devices" value="{{ default_max_devices }}" placeholder="max TB">
    <button type="submit">Cấp key</button>
  </form>
</div>

<div class="box">
  <h2>Tra cứu user</h2>
  <form method="POST" action="/web/lookup" class="row">
    <input name="user_id" placeholder="user_id">
    <button type="submit">Tra cứu</button>
  </form>
  {% if lookup %}
  <div style="margin-top:8px">
    <div>User: <b class="user">{{ lookup.user_id }}</b></div>
    <div>Key: <code class="key">{{ lookup.key }}</code></div>
    <div>Chủ: {{ lookup.owner }}</div>
    <div>Hết hạn: {{ lookup.expiresAt }}</div>
    <div>Còn: {{ lookup.daysLeft }} ngày</div>
    <div>Thiết bị: {{ lookup.devicesUsed }}/{{ lookup.maxDevices }}</div>
  </div>
  {% endif %}
</div>

<div class="box">
  <h2>Log gần đây</h2>
  <div class="scroll"><table>
    <tr><th>Thời gian</th><th>Sự kiện</th><th>Dữ liệu</th></tr>
    {% for l in logs %}
    <tr><td>{{ l.time }}</td><td>{{ l.event }}</td><td>{{ l.data }}</td></tr>
    {% endfor %}
  </table></div>
</div>
"""


@app.route("/")
def web_index():
    me = current_user()
    if not me:
        return redirect(url_for("login"))
    logs = keymod.read_json(keymod.LOG_FILE, [])[-20:]
    logs.reverse()
    body = render_template_string(
        DASHBOARD_BODY, me=me, s=compute_stats(), logs=logs, lookup=None,
        default_days=DEFAULT_DAYS, default_max_devices=DEFAULT_MAX_DEVICES,
    )
    return page("Dashboard", me, body, "dashboard")


# ---------------- KEYS ----------------


KEYS_BODY = """
<h1>DANH SÁCH KEY</h1>
<div class="box">
  <form method="POST" action="/web/create" class="row">
    <input name="days" value="30" placeholder="số ngày">
    <input name="owner" placeholder="chủ sở hữu">
    <input name="max_devices" value="1" placeholder="max TB">
    <input name="parent" placeholder="key cha">
    <button type="submit">Tạo</button>
  </form>
</div>
<div class="box"><div class="scroll"><table>
  <tr><th>Key</th><th>Chủ</th><th>User</th><th>Tạo bởi</th><th>Cha</th><th>Trạng thái</th><th>Block</th><th>TB</th><th>Còn</th><th>Hết hạn</th><th>Hành động</th></tr>
  {% for k in keys %}
  <tr>
    <td><code class="key">{{ k.key }}</code></td>
    <td>{{ k.owner }}</td>
    <td class="user">{{ k.userId or '-' }}</td>
    <td class="ctv">{{ k.createdBy or '-' }}</td>
    <td><code style="font-size:11px">{{ k.parent or '-' }}</code></td>
    <td class="{{ 'on' if k.active else 'off' }}">{{ 'ON' if k.active else 'OFF' }}</td>
    <td class="{{ 'blk' if k.blocked else '' }}">{{ 'B' if k.blocked else '-' }}</td>
    <td>{{ k.devicesUsed }}/{{ k.maxDevices }}</td>
    <td>{{ k.daysLeft }}d</td>
    <td>{{ k.expiresAtText }}</td>
    <td style="min-width:200px">
      <form method="POST" action="/web/adddays" style="display:flex;gap:4px;margin:0">
        <input type="hidden" name="key" value="{{ k.key }}">
        <input name="days" value="7" style="width:50px">
        <button type="submit" class="neutral">+ngày</button>
      </form>
      <form method="POST" action="/web/revoke" style="display:inline">
        <input type="hidden" name="key" value="{{ k.key }}">
        <button type="submit" class="neutral">Thu hồi</button>
      </form>
      <form method="POST" action="/web/resetdev" style="display:inline">
        <input type="hidden" name="key" value="{{ k.key }}">
        <button type="submit" class="neutral">Reset</button>
      </form>
      <form method="POST" action="/web/blockkey" style="display:inline">
        <input type="hidden" name="key" value="{{ k.key }}">
        <button type="submit" class="danger">Block</button>
      </form>
      <form method="POST" action="/web/delete" style="display:inline">
        <input type="hidden" name="key" value="{{ k.key }}">
        <button type="submit" class="danger">Xóa</button>
      </form>
    </td>
  </tr>
  {% endfor %}
</table>
{% if not keys %}<div class="empty">Chưa có key nào.</div>{% endif %}
</div></div>
"""


@app.route("/keys")
def web_keys():
    me = current_user()
    if not me:
        return redirect(url_for("login"))
    body = render_template_string(KEYS_BODY, me=me, keys=keymod.list_keys())
    return page("Keys", me, body, "keys")


# ---------------- TREE ----------------


TREE_BODY = """
<h1>CÂY KEY</h1>
<div class="box">
  <p style="font-size:12px;color:#8b949e">Cấu trúc phân cấp key theo cha-con.</p>
  <div class="tree">{{ tree_text or 'Chưa có key nào.' }}</div>
</div>
<div class="box">
  <h2>Gán key vào cây</h2>
  <form method="POST" action="/web/tree/attach" class="row">
    <input name="key" placeholder="key con">
    <input name="parent" placeholder="key cha">
    <button type="submit">Gán</button>
  </form>
  <form method="POST" action="/web/tree/detach" class="row">
    <input name="key" placeholder="key cần tách">
    <button type="submit" class="neutral">Tách khỏi cha</button>
  </form>
</div>
"""


@app.route("/tree")
def web_tree():
    me = current_user()
    if not me:
        return redirect(url_for("login"))
    tree_view = keymod.build_tree_view()
    lines = keymod.render_tree_text(tree_view)
    body = render_template_string(TREE_BODY, me=me, tree_text="\n".join(lines))
    return page("Cây Key", me, body, "tree")


# ---------------- DEVICES ----------------


DEVICES_BODY = """
<h1>THIẾT BỊ</h1>
<div class="box"><div class="scroll"><table>
  <tr><th>Device ID</th><th>Key</th><th>IP</th><th>Lần đầu</th><th>Lần cuối</th><th>Số lần</th><th>Block</th><th>Hành động</th></tr>
  {% for d in devices %}
  <tr>
    <td>{{ d.device_id }}</td>
    <td><code class="key">{{ d.key }}</code></td>
    <td>{{ d.ip }}</td>
    <td>{{ d.firstSeenText }}</td>
    <td>{{ d.lastSeenText }}</td>
    <td>{{ d.count }}</td>
    <td class="{{ 'blk' if d.blocked else '' }}">{{ 'CÓ' if d.blocked else '-' }}</td>
    <td>
      {% if d.blocked %}
      <form method="POST" action="/web/unblockdev" style="display:inline">
        <input type="hidden" name="device_id" value="{{ d.device_id }}">
        <button type="submit" class="neutral">Bỏ block</button>
      </form>
      {% else %}
      <form method="POST" action="/web/blockdev" style="display:inline">
        <input type="hidden" name="device_id" value="{{ d.device_id }}">
        <input type="hidden" name="key" value="{{ d.key }}">
        <button type="submit" class="danger">Block</button>
      </form>
      {% endif %}
    </td>
  </tr>
  {% endfor %}
</table>
{% if not devices %}<div class="empty">Chưa có thiết bị nào.</div>{% endif %}
</div></div>
"""


@app.route("/devices")
def web_devices():
    me = current_user()
    if not me:
        return redirect(url_for("login"))
    devices_map = keymod.load_devices()
    items = []
    for k, devs in devices_map.items():
        for dev_id, info in devs.items():
            items.append({
                "device_id": dev_id,
                "key": k,
                "ip": info.get("ip"),
                "firstSeenText": keymod.fmt_time(info.get("firstSeen", 0)),
                "lastSeenText": keymod.fmt_time(info.get("lastSeen", 0)),
                "count": info.get("count", 0),
                "blocked": keymod.is_device_blocked(dev_id),
            })
    body = render_template_string(DEVICES_BODY, me=me, devices=items)
    return page("Thiết bị", me, body, "devices")


# ---------------- BLOCKS ----------------


BLOCKS_BODY = """
<h1>BLOCK LIST</h1>
<div class="box">
  <h2>Key bị block</h2>
  <table>
    <tr><th>Key</th><th>Lý do</th><th>Thời gian</th><th>Hành động</th></tr>
    {% for k, v in blocked.get('keys', {}).items() %}
    <tr>
      <td><code class="key">{{ k }}</code></td>
      <td>{{ v.reason }}</td>
      <td>{{ fmt(v.time) }}</td>
      <td>
        <form method="POST" action="/web/unblockkey" style="display:inline">
          <input type="hidden" name="key" value="{{ k }}">
          <button type="submit" class="neutral">Bỏ block</button>
        </form>
      </td>
    </tr>
    {% endfor %}
  </table>
  {% if not blocked.get('keys') %}<div class="empty">Không có key bị block.</div>{% endif %}
</div>
<div class="box">
  <h2>Thiết bị bị block</h2>
  <table>
    <tr><th>Device</th><th>Key</th><th>Lý do</th><th>Thời gian</th><th>Hành động</th></tr>
    {% for d, v in blocked.get('devices', {}).items() %}
    <tr>
      <td>{{ d }}</td>
      <td><code class="key">{{ v.key }}</code></td>
      <td>{{ v.reason }}</td>
      <td>{{ fmt(v.time) }}</td>
      <td>
        <form method="POST" action="/web/unblockdev" style="display:inline">
          <input type="hidden" name="device_id" value="{{ d }}">
          <button type="submit" class="neutral">Bỏ block</button>
        </form>
      </td>
    </tr>
    {% endfor %}
  </table>
  {% if not blocked.get('devices') %}<div class="empty">Không có thiết bị bị block.</div>{% endif %}
</div>
<div class="box">
  <h2>Block thủ công</h2>
  <form method="POST" action="/web/blockkey" class="row">
    <input name="key" placeholder="key cần block">
    <input name="reason" placeholder="lý do">
    <button type="submit" class="danger">Block key</button>
  </form>
  <form method="POST" action="/web/blockdev" class="row">
    <input name="device_id" placeholder="device_id cần block">
    <input name="reason" placeholder="lý do">
    <button type="submit" class="danger">Block thiết bị</button>
  </form>
</div>
"""


@app.route("/blocks")
def web_blocks():
    me = current_user()
    if not me:
        return redirect(url_for("login"))
    body = render_template_string(BLOCKS_BODY, me=me,
                                  blocked=keymod.load_blocked(), fmt=keymod.fmt_time)
    return page("Block", me, body, "blocks")


# ---------------- CTV ----------------


CTV_BODY = """
<h1>QUẢN LÝ CTV</h1>
<div class="box">
  <h2>Thêm CTV</h2>
  <form method="POST" action="/web/addctv" class="row">
    <input name="user_id" placeholder="user_id telegram">
    <input name="name" placeholder="tên">
    <input name="max_keys" value="{{ default_max_keys }}" placeholder="max keys">
    <input name="max_days" value="{{ default_max_days }}" placeholder="max days">
    <button type="submit">Thêm</button>
  </form>
</div>
<div class="box"><table>
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
        <button type="submit" class="neutral">{{ 'Tắt' if rec.active else 'Bật' }}</button>
      </form>
      <form method="POST" action="/web/removectv" style="display:inline">
        <input type="hidden" name="user_id" value="{{ uid }}">
        <button type="submit" class="danger">Xóa</button>
      </form>
    </td>
  </tr>
  {% endfor %}
</table>
{% if not ctv %}<div class="empty">Chưa có CTV nào.</div>{% endif %}
</div>
"""


@app.route("/ctv")
def web_ctv():
    me = current_user()
    if not me or not authmod.has_permission(me["role"], "ctv"):
        return make_response("Không có quyền.", 403)
    body = render_template_string(
        CTV_BODY, me=me, ctv=load_ctv(),
        default_max_keys=CTV_MAX_KEYS, default_max_days=CTV_MAX_DAYS,
        fmt=keymod.fmt_time,
    )
    return page("CTV", me, body, "ctv")


# ---------------- ACCOUNTS ----------------


ACCOUNTS_BODY = """
<h1>QUẢN LÝ TÀI KHOẢN</h1>
<div class="box">
  <h2>Tạo tài khoản</h2>
  <form method="POST" action="/accounts/create" class="row">
    <input name="username" placeholder="tài khoản">
    <input name="password" type="password" placeholder="mật khẩu">
    <select name="role">
      <option value="admin">admin</option>
      <option value="operator">operator</option>
      <option value="ctv">ctv</option>
      <option value="viewer" selected>viewer</option>
    </select>
    <button type="submit">Tạo</button>
  </form>
  {% if error %}<div class="err">{{ error }}</div>{% endif %}
</div>
<div class="box"><table>
  <tr><th>Tài khoản</th><th>Vai trò</th><th>Trạng thái</th><th>Key</th><th>Tạo lúc</th><th>Hành động</th></tr>
  {% for a in accounts %}
  <tr>
    <td class="user">{{ a.username }}</td>
    <td><span class="tag {{ a.role }}">{{ a.role }}</span></td>
    <td class="{{ 'on' if a.active else 'off' }}">{{ 'ON' if a.active else 'OFF' }}</td>
    <td><code class="key" style="font-size:11px">{{ a.key or '-' }}</code></td>
    <td>{{ a.createdAtText }}</td>
    <td>
      <form method="POST" action="/accounts/toggle" style="display:inline">
        <input type="hidden" name="username" value="{{ a.username }}">
        <button type="submit" class="neutral">{{ 'Tắt' if a.active else 'Bật' }}</button>
      </form>
      <form method="POST" action="/accounts/role" style="display:inline">
        <input type="hidden" name="username" value="{{ a.username }}">
        <select name="role" style="width:auto;display:inline">
          <option value="admin">admin</option>
          <option value="operator">operator</option>
          <option value="ctv">ctv</option>
          <option value="viewer">viewer</option>
        </select>
        <button type="submit" class="neutral">Đổi quyền</button>
      </form>
      <form method="POST" action="/accounts/remove" style="display:inline">
        <input type="hidden" name="username" value="{{ a.username }}">
        <button type="submit" class="danger">Xóa</button>
      </form>
    </td>
  </tr>
  {% endfor %}
</table></div>
"""


@app.route("/accounts")
def accounts_page():
    me = current_user()
    if not me or me["role"] != "admin":
        return make_response("Không có quyền.", 403)
    body = render_template_string(
        ACCOUNTS_BODY, me=me,
        accounts=authmod.list_accounts(),
        error=request.args.get("error", ""),
    )
    return page("Tài khoản", me, body, "accounts")


# ---------------- LOGS ----------------


LOGS_BODY = """
<h1>LOG</h1>
<div class="box">
  <form method="GET" action="/logs" class="row">
    <input name="n" value="{{ n }}" placeholder="số dòng">
    <button type="submit" class="neutral">Xem</button>
  </form>
</div>
<div class="box"><div class="scroll"><table>
  <tr><th>Thời gian</th><th>Sự kiện</th><th>Dữ liệu</th></tr>
  {% for l in logs %}
  <tr><td>{{ l.time }}</td><td>{{ l.event }}</td><td>{{ l.data }}</td></tr>
  {% endfor %}
</table>
{% if not logs %}<div class="empty">Chưa có log.</div>{% endif %}
</div></div>
"""


@app.route("/logs")
def web_logs():
    me = current_user()
    if not me:
        return redirect(url_for("login"))
    n = int(request.args.get("n", 100))
    logs = keymod.read_json(keymod.LOG_FILE, [])[-n:]
    logs.reverse()
    body = render_template_string(LOGS_BODY, me=me, logs=logs, n=n)
    return page("Log", me, body, "logs")


# ---------------- TRANG TELEGRAM (FIX) ----------------


TELEGRAM_BODY = """
<h1>TELEGRAM BOT</h1>
<div class="box">
  <h2>Trạng thái</h2>
  <div class="status {{ 'ok' if info.webhook_set else 'err' }}">
    Webhook: {{ 'ĐÃ ĐĂNG KÝ' if info.webhook_set else 'CHƯA ĐĂNG KÝ' }}
  </div>
  <div class="status {{ 'ok' if info.getme_ok else 'err' }}">
    Bot API: {{ 'HOẠT ĐỘNG' if info.getme_ok else 'LỖI - ' + (info.getme_error or '') }}
  </div>
  <div>Bot username: <b>{{ info.bot_username or '-' }}</b></div>
  <div>Webhook URL: <code style="font-size:11px">{{ info.webhook_url or '-' }}</code></div>
  <div>Pending updates: {{ info.pending_updates }}</div>
  <div>Render URL: <code style="font-size:11px">{{ info.render_url or 'CHƯA CÓ' }}</code></div>
</div>

<div class="box">
  <h2>Hành động</h2>
  <form method="POST" action="/telegram/set-webhook" style="margin-bottom:6px">
    <button type="submit">Đăng ký webhook</button>
  </form>
  <form method="POST" action="/telegram/delete-webhook" style="margin-bottom:6px">
    <button type="submit" class="danger">Xóa webhook</button>
  </form>
  <form method="POST" action="/telegram/test" style="margin-bottom:6px">
    <input name="chat_id" placeholder="chat_id test">
    <button type="submit" class="neutral">Gửi tin nhắn test</button>
  </form>
  <form method="POST" action="/telegram/getme">
    <button type="submit" class="neutral">Kiểm tra Bot API</button>
  </form>
</div>

<div class="box">
  <h2>Thông tin</h2>
  <div>BOT_TOKEN: <code>{{ info.token_preview }}</code></div>
  <div>ADMIN_IDS: <code>{{ info.admin_ids }}</code></div>
  <div style="font-size:12px;color:#8b949e;margin-top:8px">
    Nếu webhook không đăng ký được, hãy đảm bảo biến RENDER_EXTERNAL_URL đã có.
    Render tự đặt biến này khi deploy web service.
  </div>
</div>
"""


def get_telegram_info():
    info = {
        "webhook_set": False,
        "webhook_url": None,
        "pending_updates": 0,
        "getme_ok": False,
        "getme_error": None,
        "bot_username": None,
        "render_url": os.environ.get("RENDER_EXTERNAL_URL"),
        "token_preview": (BOT_TOKEN[:10] + "...") if BOT_TOKEN else "THIẾU",
        "admin_ids": ", ".join(ADMIN_IDS),
    }
    if not BOT_TOKEN:
        return info
    try:
        r = requests.get(f"{API}/getWebhookInfo", timeout=10)
        if r.status_code == 200:
            d = r.json().get("result", {})
            info["webhook_url"] = d.get("url")
            info["webhook_set"] = bool(d.get("url"))
            info["pending_updates"] = d.get("pending_update_count", 0)
    except Exception as e:
        info["getme_error"] = str(e)
    try:
        r = requests.get(f"{API}/getMe", timeout=10)
        if r.status_code == 200 and r.json().get("ok"):
            info["getme_ok"] = True
            info["bot_username"] = r.json()["result"].get("username")
        else:
            info["getme_error"] = r.text[:120]
    except Exception as e:
        info["getme_error"] = str(e)
    return info


@app.route("/telegram")
def web_telegram():
    me = current_user()
    if not me or me["role"] != "admin":
        return make_response("Không có quyền.", 403)
    body = render_template_string(TELEGRAM_BODY, me=me, info=get_telegram_info())
    return page("Telegram", me, body, "telegram")


@app.route("/telegram/set-webhook", methods=["POST"])
def telegram_set_webhook():
    me = current_user()
    if not me or me["role"] != "admin":
        return make_response("Không có quyền.", 403)
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        return redirect(url_for("web_telegram"))
    webhook_url = f"{url}/webhook/{BOT_TOKEN}"
    try:
        r = requests.get(f"{API}/setWebhook", params={
            "url": webhook_url,
            "drop_pending_updates": "true",
            "allowed_updates": json.dumps(["message", "callback_query"]),
        }, timeout=15)
        print("[TG] setWebhook:", r.text[:200])
    except Exception as e:
        print("[TG] setWebhook loi:", e)
    return redirect(url_for("web_telegram"))


@app.route("/telegram/delete-webhook", methods=["POST"])
def telegram_delete_webhook():
    me = current_user()
    if not me or me["role"] != "admin":
        return make_response("Không có quyền.", 403)
    try:
        r = requests.get(f"{API}/deleteWebhook",
                         params={"drop_pending_updates": "true"}, timeout=15)
        print("[TG] deleteWebhook:", r.text[:200])
    except Exception as e:
        print("[TG] deleteWebhook loi:", e)
    return redirect(url_for("web_telegram"))


@app.route("/telegram/test", methods=["POST"])
def telegram_test():
    me = current_user()
    if not me or me["role"] != "admin":
        return make_response("Không có quyền.", 403)
    chat_id = request.form.get("chat_id", "").strip()
    if chat_id:
        send_message(chat_id, "🔑 Test từ key server. Bot hoạt động.")
    return redirect(url_for("web_telegram"))


@app.route("/telegram/getme", methods=["POST"])
def telegram_getme():
    me = current_user()
    if not me or me["role"] != "admin":
        return make_response("Không có quyền.", 403)
    try:
        requests.get(f"{API}/getMe", timeout=10)
    except Exception:
        pass
    return redirect(url_for("web_telegram"))


# ---------------- MY PANEL ----------------


MY_PANEL_BODY = """
<h1>XIN CHÀO {{ me.username }}</h1>
<div class="box">
  <div>Tài khoản: <b class="user">{{ me.username }}</b></div>
  <div>Vai trò: <span class="tag {{ me.role }}">{{ me.role }}</span></div>
  <div>Ngày tạo: {{ created }}</div>
</div>
<div class="box">
  <h2>KEY CỦA BẠN</h2>
  {% if kr %}
    <div class="key"><code>{{ kr.key }}</code></div>
    <div>Chủ: {{ kr.owner }}</div>
    <div>Trạng thái: <span class="{{ 'on' if kr.active else 'off' }}">{{ 'ON' if kr.active else 'OFF' }}</span></div>
    <div>Block: <span class="{{ 'blk' if kr.blocked else '' }}">{{ 'CÓ' if kr.blocked else 'KHÔNG' }}</span></div>
    <div>Hết hạn: {{ kr.expiresAtText }}</div>
    <div>Còn lại: {{ kr.daysLeft }} ngày</div>
    <div>Thiết bị: {{ kr.devicesUsed }}/{{ kr.maxDevices }}</div>
    <div>Chữ ký: <code style="font-size:11px">{{ kr.signature }}</code></div>
  {% else %}
    <div class="empty">Bạn chưa có key.</div>
    <form method="POST" action="/my/getkey"><button type="submit">NHẬN KEY</button></form>
  {% endif %}
</div>
{% if kr %}
<div class="box">
  <h2>THIẾT BỊ</h2>
  <table>
    <tr><th>Device ID</th><th>IP</th><th>Lần đầu</th><th>Lần cuối</th><th>Số lần</th></tr>
    {% for d, info in devices.items() %}
    <tr><td>{{ d }}</td><td>{{ info.ip }}</td><td>{{ fmt(info.firstSeen) }}</td><td>{{ fmt(info.lastSeen) }}</td><td>{{ info.count }}</td></tr>
    {% endfor %}
  </table>
  {% if not devices %}<div class="empty">Chưa có thiết bị nào.</div>{% endif %}
</div>
{% endif %}
<div class="box">
  <h2>ĐỔI MẬT KHẨU</h2>
  <form method="POST" action="/my/changepw">
    <input name="old_password" type="password" placeholder="mật khẩu cũ">
    <input name="new_password" type="password" placeholder="mật khẩu mới (≥6)">
    <button type="submit">Đổi mật khẩu</button>
  </form>
  {% if error %}<div class="err">{{ error }}</div>{% endif %}
  {% if success %}<div class="ok">{{ success }}</div>{% endif %}
</div>
"""


@app.route("/my")
@app.route("/my/")
def my_panel():
    me = current_user()
    if not me:
        return redirect(url_for("login"))
    rec = authmod.get_account(me["uid"])
    key = rec.get("key")
    kr = keymod.get_key_info(key) if key else None
    devices = keymod.load_devices().get(key, {}) if key else {}
    body = render_template_string(
        MY_PANEL_BODY, me=me,
        created=keymod.fmt_time(rec.get("createdAt", keymod.now_ms())),
        kr=kr, devices=devices, fmt=keymod.fmt_time,
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
    )
    return page("Bảng điều khiển", me, body, "my")


@app.route("/my/getkey", methods=["POST"])
def my_getkey():
    me = current_user()
    if not me:
        return redirect(url_for("login"))
    if not AUTO_ISSUE_ENABLED:
        return redirect(url_for("my_panel", error="Chức năng cấp key đang tắt."))
    rec = authmod.get_account(me["uid"])
    existing = rec.get("key")
    if existing:
        kr = keymod.load_keys().get(existing)
        if kr and kr.get("active") and keymod.now_ms() < kr["expiresAt"]:
            return redirect(url_for("my_panel"))
    user_id = rec.get("telegramId") or f"web_{me['uid']}"
    get_or_create_key_for_user(
        user_id, owner=rec["username"],
        days=DEFAULT_DAYS, max_devices=DEFAULT_MAX_DEVICES,
        account_uid=me["uid"],
    )
    return redirect(url_for("my_panel"))


@app.route("/my/changepw", methods=["POST"])
def my_changepw():
    me = current_user()
    if not me:
        return redirect(url_for("login"))
    ok, err = authmod.change_account_password(
        me["uid"],
        request.form.get("old_password", ""),
        request.form.get("new_password", ""),
    )
    if not ok:
        return redirect(url_for("my_panel", error={
            "not_found": "Không tìm thấy tài khoản.",
            "wrong_password": "Mật khẩu cũ không đúng.",
            "too_short": "Mật khẩu mới quá ngắn.",
        }.get(err, "Lỗi.")))
    return redirect(url_for("my_panel", success="Đã đổi mật khẩu."))


# ---------------- WEB ACTIONS ----------------


@app.route("/web/create", methods=["POST"])
@require_login("write")
def web_create():
    days = int(request.form.get("days", 30))
    owner = request.form.get("owner", "unknown")
    max_dev = int(request.form.get("max_devices", DEFAULT_MAX_DEVICES))
    parent = request.form.get("parent", "").strip() or None
    me = current_user()
    keymod.create_key(days, owner, max_dev, created_by=me["username"], parent_key=parent)
    return redirect(request.referrer or url_for("web_index"))


@app.route("/web/issue", methods=["POST"])
@require_login("issue")
def web_issue():
    user_id = request.form.get("user_id", "").strip()
    if not user_id:
        return redirect(request.referrer or url_for("web_index"))
    days = int(request.form.get("days", DEFAULT_DAYS))
    owner = request.form.get("owner", "").strip() or f"user_{user_id}"
    max_dev = int(request.form.get("max_devices", DEFAULT_MAX_DEVICES))
    me = current_user()
    get_or_create_key_for_user(user_id, owner=owner, days=days,
                               max_devices=max_dev, created_by=me["username"])
    return redirect(request.referrer or url_for("web_index"))


@app.route("/web/lookup", methods=["POST"])
@require_login("read")
def web_lookup():
    user_id = request.form.get("user_id", "").strip()
    key = get_key_by_user(user_id)
    lookup = None
    if key:
        info = keymod.get_key_info(key)
        if info:
            lookup = {
                "user_id": user_id, "key": key, "owner": info["owner"],
                "expiresAt": info["expiresAtText"], "daysLeft": info["daysLeft"],
                "devicesUsed": info["devicesUsed"], "maxDevices": info["maxDevices"],
            }
    logs = keymod.read_json(keymod.LOG_FILE, [])[-20:]
    logs.reverse()
    body = render_template_string(
        DASHBOARD_BODY, me=current_user(), s=compute_stats(), logs=logs,
        lookup=lookup, default_days=DEFAULT_DAYS, default_max_devices=DEFAULT_MAX_DEVICES,
    )
    return page("Dashboard", current_user(), body, "dashboard")


@app.route("/web/adddays", methods=["POST"])
@require_login("write")
def web_adddays():
    keymod.add_days(request.form.get("key", ""), int(request.form.get("days", 0)))
    return redirect(request.referrer or url_for("web_keys"))


@app.route("/web/revoke", methods=["POST"])
@require_login("write")
def web_revoke():
    keymod.revoke_key(request.form.get("key", ""))
    return redirect(request.referrer or url_for("web_keys"))


@app.route("/web/resetdev", methods=["POST"])
@require_login("write")
def web_resetdev():
    keymod.reset_devices(request.form.get("key", ""))
    return redirect(request.referrer or url_for("web_keys"))


@app.route("/web/delete", methods=["POST"])
@require_login("delete")
def web_delete():
    keymod.delete_key(request.form.get("key", ""))
    return redirect(request.referrer or url_for("web_keys"))


@app.route("/web/blockkey", methods=["POST"])
@require_login("block")
def web_blockkey():
    keymod.block_key(request.form.get("key", ""), request.form.get("reason", "manual"))
    return redirect(request.referrer or url_for("web_blocks"))


@app.route("/web/unblockkey", methods=["POST"])
@require_login("block")
def web_unblockkey():
    keymod.unblock_key(request.form.get("key", ""))
    return redirect(request.referrer or url_for("web_blocks"))


@app.route("/web/blockdev", methods=["POST"])
@require_login("block")
def web_blockdev():
    keymod.block_device(
        request.form.get("key", ""),
        request.form.get("device_id", ""),
        request.form.get("reason", "manual"),
    )
    return redirect(request.referrer or url_for("web_blocks"))


@app.route("/web/unblockdev", methods=["POST"])
@require_login("block")
def web_unblockdev():
    keymod.unblock_device(request.form.get("device_id", ""))
    return redirect(request.referrer or url_for("web_blocks"))


@app.route("/web/tree/attach", methods=["POST"])
@require_login("write")
def web_tree_attach():
    key = request.form.get("key", "").strip()
    parent = request.form.get("parent", "").strip()
    keys = keymod.load_keys()
    if key in keys and parent in keys:
        keys[key]["parent"] = parent
        keymod.save_keys(keys)
        keymod.remove_tree_node(key)
        keymod.add_tree_node(key, parent_key=parent, owner=keys[key].get("owner"))
    return redirect(url_for("web_tree"))


@app.route("/web/tree/detach", methods=["POST"])
@require_login("write")
def web_tree_detach():
    key = request.form.get("key", "").strip()
    keys = keymod.load_keys()
    if key in keys:
        keys[key]["parent"] = None
        keymod.save_keys(keys)
        keymod.remove_tree_node(key)
        keymod.add_tree_node(key, parent_key=None, owner=keys[key].get("owner"))
    return redirect(url_for("web_tree"))


@app.route("/web/addctv", methods=["POST"])
@require_login("ctv")
def web_addctv():
    user_id = request.form.get("user_id", "").strip()
    if user_id:
        add_ctv(user_id,
                name=request.form.get("name", "").strip() or None,
                max_keys=int(request.form.get("max_keys", CTV_MAX_KEYS)),
                max_days=int(request.form.get("max_days", CTV_MAX_DAYS)))
    return redirect(url_for("web_ctv"))


@app.route("/web/removectv", methods=["POST"])
@require_login("ctv")
def web_removectv():
    remove_ctv(request.form.get("user_id", "").strip())
    return redirect(url_for("web_ctv"))


@app.route("/web/toggle_ctv", methods=["POST"])
@require_login("ctv")
def web_toggle_ctv():
    toggle_ctv(request.form.get("user_id", "").strip())
    return redirect(url_for("web_ctv"))


@app.route("/accounts/create", methods=["POST"])
@require_login("admin")
def accounts_create():
    u = request.form.get("username", "").strip()
    p = request.form.get("password", "")
    ok, err = authmod.register_account(u, p)
    if ok:
        uid, _ = authmod.find_account_by_username(u)
        if uid:
            authmod.set_account_role(uid, request.form.get("role", "viewer"))
        return redirect(url_for("accounts_page"))
    return redirect(url_for("accounts_page", error=err))


@app.route("/accounts/remove", methods=["POST"])
@require_login("admin")
def accounts_remove():
    u = request.form.get("username", "")
    uid, _ = authmod.find_account_by_username(u)
    me = current_user()
    if uid and me and u != me["username"]:
        authmod.delete_account(uid)
    return redirect(url_for("accounts_page"))


@app.route("/accounts/toggle", methods=["POST"])
@require_login("admin")
def accounts_toggle():
    uid, _ = authmod.find_account_by_username(request.form.get("username", ""))
    if uid:
        authmod.toggle_account(uid)
    return redirect(url_for("accounts_page"))


@app.route("/accounts/role", methods=["POST"])
@require_login("admin")
def accounts_role():
    uid, _ = authmod.find_account_by_username(request.form.get("username", ""))
    if uid:
        authmod.set_account_role(uid, request.form.get("role", "viewer"))
    return redirect(url_for("accounts_page"))


# ---------------- API JSON ----------------


@app.route("/api/health")
def api_health():
    return jsonify({
        "ok": True, "service": "key-server",
        "status": "online", "time": keymod.fmt_time(keymod.now_ms()),
        "telegram": get_telegram_info(),
    })


@app.route("/api/verify", methods=["POST"])
def api_verify():
    data = request.get_json(force=True, silent=True) or {}
    key = data.get("key")
    device_id = data.get("device_id") or data.get("deviceId")
    dylibs = data.get("dylibs")
    if not key or not device_id:
        return jsonify({"ok": False, "error": "missing_params"}), 400
    result = keymod.verify_key(key, device_id, get_client_ip(request),
                               request.headers.get("User-Agent", "unknown"), dylibs)
    return jsonify(result), (200 if result["ok"] else 403)


@app.route("/api/info", methods=["POST"])
def api_info():
    data = request.get_json(force=True, silent=True) or {}
    info = keymod.get_key_info(data.get("key"))
    if not info:
        return jsonify({"ok": False, "error": "key_not_found"}), 404
    return jsonify({"ok": True, **info})


@app.route("/api/tree")
def api_tree():
    return jsonify({"ok": True, "tree": keymod.build_tree_view()})


@app.route("/api/stats")
@require_admin_token
def api_stats():
    return jsonify({"ok": True, **compute_stats()})


# ---------------- TELEGRAM HANDLER ----------------


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

    print(f"[TG] update from {user_id}: {cmd}")

    if cmd == "/start":
        s = "🔑 Key server đang hoạt động.\n"
        s += "/code - nhận key\n/mykey - xem key\n/verify &lt;key&gt; &lt;dev&gt;\n/info &lt;key&gt;\n/days &lt;key&gt;\n"
        if perm:
            s += "/create /issue /adddays /devices\n/tree\n"
        if admin:
            s += "/setexp /revoke /resetdev /delete\n"
            s += "/addctv /removectv /togglectv /ctvlist\n"
            s += "/blockdev /unblockdev /blockkey /unblockkey /blocklist\n"
            s += "/list /logs"
        send_message(chat_id, s)
        return

    if cmd == "/tree":
        tree_view = keymod.build_tree_view()
        lines = keymod.render_tree_text(tree_view)
        send_message(chat_id, "🌳 CÂY KEY\n" + ("\n".join(lines) if lines else "Chưa có key."))
        return

    if cmd == "/code":
        if not AUTO_ISSUE_ENABLED:
            send_message(chat_id, "Chức năng cấp key đang tắt.")
            return
        result = get_or_create_key_for_user(user_id, owner=f"tg_{user_id}")
        send_message(chat_id, f"{'Đã cấp' if result['created'] else 'Bạn đã có'} key.\n"
                              f"<code>{result['key']}</code>\n"
                              f"Còn: {keymod.get_days_left(result['key'])} ngày")
        return

    if cmd == "/mykey":
        k = get_key_by_user(user_id)
        if not k:
            send_message(chat_id, "Chưa có key. Dùng /code.")
            return
        info = keymod.get_key_info(k)
        send_message(chat_id, f"Key: <code>{k}</code>\n"
                              f"Còn: {info['daysLeft']} ngày\n"
                              f"TB: {info['devicesUsed']}/{info['maxDevices']}")
        return

    if cmd == "/verify":
        if len(parts) < 3:
            send_message(chat_id, "Cú pháp: /verify <key> <device_id>")
            return
        result = keymod.verify_key(parts[1], parts[2], "telegram", f"user:{user_id}")
        if not result["ok"]:
            send_message(chat_id, f"Thất bại: {result['error']}")
            return
        send_message(chat_id, f"Hợp lệ.\nChủ: {result['owner']}\n"
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
        send_message(chat_id, f"Key: <code>{info['key']}</code>\nChủ: {info['owner']}\n"
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
        send_message(chat_id, f"Còn: {d} ngày" if d is not None else "Key không tồn tại.")
        return

    if cmd == "/create":
        if not perm:
            send_message(chat_id, "Không có quyền.")
            return
        days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 30
        owner = parts[2] if len(parts) > 2 else "unknown"
        max_dev = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else DEFAULT_MAX_DEVICES
        if ctv and not admin:
            ok, err = ctv_can_create(user_id, days)
            if not ok:
                send_message(chat_id, f"Không thể tạo: {err}")
                return
        k, exp, sig = keymod.create_key(days, owner, max_dev,
                                        created_by=user_id if ctv else None)
        if ctv:
            increment_ctv_count(user_id)
        send_message(chat_id, f"Key mới:\n<code>{k}</code>\n"
                              f"Chủ: {owner}\nHạn: {keymod.fmt_time(exp)}\n"
                              f"Max TB: {max_dev}")
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
        result = get_or_create_key_for_user(target, owner=f"user_{target}", days=days,
                                            created_by=user_id if ctv else None)
        send_message(chat_id, f"{'Đã tạo' if result['created'] else 'Đã có'} key cho {target}:\n"
                              f"<code>{result['key']}</code>")
        return

    if cmd == "/adddays":
        if not perm:
            send_message(chat_id, "Không có quyền.")
            return
        if len(parts) < 3 or not parts[2].lstrip("-").isdigit():
            send_message(chat_id, "Cú pháp: /adddays <key> <days>")
            return
        new_exp = keymod.add_days(parts[1], int(parts[2]))
        send_message(chat_id, f"Hết hạn mới: {keymod.fmt_time(new_exp)}" if new_exp else "Key không tồn tại.")
        return

    if cmd == "/list":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        keys = keymod.list_keys()
        if not keys:
            send_message(chat_id, "Chưa có key.")
            return
        lines = []
        for k in keys[:30]:
            lines.append(f"<code>{k['key']}</code> | {k['owner']} | {k['daysLeft']}d")
        send_message(chat_id, "\n".join(lines))
        return

    if cmd == "/logs":
        if not admin:
            send_message(chat_id, "Không có quyền.")
            return
        n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
        logs = keymod.read_json(keymod.LOG_FILE, [])[-n:]
        if not logs:
            send_message(chat_id, "Chưa có log.")
            return
        lines = [f"{l['time']} | {l['event']}" for l in logs]
        send_message(chat_id, "\n".join(lines))
        return

    send_message(chat_id, f"Lệnh không hỗ trợ: {cmd}")


# ---------------- WEBHOOK ROUTE (FIX) ----------------


@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    # Luon tra 200 de Telegram khong retry
    try:
        data = request.get_json(force=True, silent=True) or {}
        handle_update(data)
    except Exception as e:
        print("[TG] webhook exception:", e)
    return "OK", 200


# Route webhook du phong khong kem token
@app.route("/webhook", methods=["POST"])
def webhook_noprefix():
    try:
        data = request.get_json(force=True, silent=True) or {}
        handle_update(data)
    except Exception as e:
        print("[TG] webhook exception:", e)
    return "OK", 200


# ---------------- STARTUP ----------------


def set_webhook():
    # Dang ky webhook voi Telegram khi khoi dong
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        print("[TG] Thieu RENDER_EXTERNAL_URL, bo qua setWebhook.")
        WEBHOOK_INFO["last_error"] = "missing RENDER_EXTERNAL_URL"
        return
    webhook_url = f"{url}/webhook/{BOT_TOKEN}"
    try:
        r = requests.get(f"{API}/setWebhook", params={
            "url": webhook_url,
            "drop_pending_updates": "true",
            "allowed_updates": json.dumps(["message", "callback_query"]),
        }, timeout=15)
        print("[TG] setWebhook:", r.text[:200])
        d = r.json()
        if d.get("ok"):
            WEBHOOK_INFO["registered"] = True
            WEBHOOK_INFO["url"] = webhook_url
        else:
            WEBHOOK_INFO["last_error"] = d.get("description")
    except Exception as e:
        print("[TG] setWebhook loi:", e)
        WEBHOOK_INFO["last_error"] = str(e)


def check_bot():
    # Kiem tra token hop le
    try:
        r = requests.get(f"{API}/getMe", timeout=10)
        if r.status_code == 200:
            d = r.json()
            if d.get("ok"):
                print(f"[TG] Bot OK: @{d['result'].get('username')}")
                return True
        print("[TG] getMe loi:", r.text[:200])
    except Exception as e:
        print("[TG] getMe exception:", e)
    return False


# Kiem tra bot ngay khi import (cho gunicorn)
if BOT_TOKEN:
    try:
        check_bot()
    except Exception as e:
        print("[TG] Kiem tra bot that bai:", e)


if __name__ == "__main__":
    authmod.ensure_default_user()
    port = int(os.environ.get("PORT", 3000))
    if BOT_TOKEN:
        set_webhook()
    app.run(host="0.0.0.0", port=port)
