# web.py - Blueprint giao diện web Key Server
# Tác giả: MADE BY Bao Huy
# Tự chứa toàn bộ HTML, không cần thư mục templates
# Phụ thuộc: key.py, auth.py, apikey.py, db.py

import os
import json
import time
import secrets
from functools import wraps
from datetime import datetime

from flask import (
    Blueprint, request, jsonify, render_template_string,
    make_response, redirect, url_for,
)

# ---------------- IMPORT MODULE NỘI BỘ (AN TOÀN) ----------------

try:
    import key as keymod
except ImportError:
    keymod = None

try:
    import auth as authmod
except ImportError:
    authmod = None

try:
    import apikey
except ImportError:
    apikey = None

try:
    from db import (
        get_db, execute, fetchone, fetchall, insert, update, delete,
        now_ms, fmt_time, rows_to_list,
    )
except ImportError:
    def now_ms():
        return int(time.time() * 1000)
    def fmt_time(ms):
        try:
            return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return "-"

# ---------------- CẤU HÌNH ----------------

DEFAULT_DAYS = 30
DEFAULT_MAX_DEVICES = 1
if keymod:
    DEFAULT_DAYS = getattr(keymod, "DEFAULT_DAYS", 30)
    DEFAULT_MAX_DEVICES = getattr(keymod, "DEFAULT_MAX_DEVICES", 1)

CTV_MAX_DAYS = int(os.environ.get("CTV_MAX_DAYS", "30"))
CTV_MAX_KEYS = int(os.environ.get("CTV_MAX_KEYS", "50"))

web_bp = Blueprint("web", __name__)

# ---------------- CSS ----------------

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

# ---------------- LAYOUT ----------------

def nav_html(me, active=""):
    items = [
        ("/", "Dashboard", "dashboard"),
        ("/keys", "Keys", "keys"),
        ("/tree", "Cây Key", "tree"),
        ("/devices", "Thiết bị", "devices"),
        ("/blocks", "Block", "blocks"),
        ("/ctv", "CTV", "ctv"),
        ("/accounts", "Tài khoản", "accounts"),
        ("/api", "API", "api"),
        ("/logs", "Log", "logs"),
        ("/my", "Cá nhân", "my"),
    ]
    links = ""
    for url, label, name in items:
        style = ' style="background:#1f6feb;color:#fff"' if name == active else ""
        links += f'<a href="{url}"{style}>{label}</a>'
    if me:
        me_tag = (f'<span class="tag {me["role"]}">{me["username"]} '
                  f'({me["role"]})</span><a href="/logout">Thoát</a>')
    else:
        me_tag = '<a href="/login">Đăng nhập</a>'
    return (f'<div class="nav"><span class="brand">🔑 KEY SERVER</span>'
            f'{links}<span style="flex:1"></span>{me_tag}</div>')

def page(title, me, body, active=""):
    return (f'<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{title}</title>{BASE_CSS}</head><body>'
            f'{nav_html(me, active)}{body}</body></html>')

# ---------------- AUTH ----------------

def current_user():
    if not authmod:
        return None
    token = request.cookies.get("session")
    if not token:
        return None
    try:
        s = authmod.get_session(token)
        if not s:
            return None
        rec = authmod.load_accounts().get(s["uid"])
        if not rec or not rec.get("active", True):
            return None
        return {"uid": s["uid"], "username": rec["username"],
                "role": rec.get("role", "user")}
    except Exception:
        return None

def require_login(perm=None):
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            me = current_user()
            if not me:
                return redirect(url_for("web.login"))
            if perm and authmod and not authmod.has_permission(me["role"], perm):
                return make_response("Không có quyền.", 403)
            return f(*args, **kwargs)
        return wrapper
    return deco

# ---------------- STATS ----------------

def compute_stats():
    try:
        row = fetchone("""
            SELECT
              (SELECT COUNT(*) FROM keys) AS totalKeys,
              (SELECT COUNT(*) FROM keys WHERE active=1) AS activeKeys,
              (SELECT COUNT(*) FROM keys WHERE expires_at < ?) AS expiredKeys,
              (SELECT COUNT(*) FROM devices) AS totalDevices,
              (SELECT COUNT(*) FROM accounts) AS totalUsers,
              (SELECT COUNT(*) FROM ctv) AS totalCtv,
              (SELECT COUNT(*) FROM blocked WHERE type='key') AS blockedKeys,
              (SELECT COUNT(*) FROM blocked WHERE type='device') AS blockedDevices
        """, (now_ms(),))
        return dict(row) if row else {
            "totalKeys": 0, "activeKeys": 0, "expiredKeys": 0,
            "totalDevices": 0, "totalUsers": 0, "totalCtv": 0,
            "blockedKeys": 0, "blockedDevices": 0,
        }
    except Exception:
        return {
            "totalKeys": 0, "activeKeys": 0, "expiredKeys": 0,
            "totalDevices": 0, "totalUsers": 0, "totalCtv": 0,
            "blockedKeys": 0, "blockedDevices": 0,
        }

# ---------------- TEMPLATES ----------------

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
    <input name="max_devices" value="{{ default_max_devices }}" placeholder="max TB">
    <button type="submit">Cấp key</button>
  </form>
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

KEYS_BODY = """
<h1>DANH SÁCH KEY</h1>
<div class="box">
  <form method="POST" action="/web/create" class="row">
    <input name="days" value="30" placeholder="số ngày">
    <input name="owner" placeholder="chủ sở hữu">
    <input name="max_devices" value="1" placeholder="max TB">
    <button type="submit">Tạo key</button>
  </form>
</div>
<div class="box"><div class="scroll"><table>
  <tr><th>Key</th><th>Chủ</th><th>Trạng thái</th><th>TB</th><th>Còn</th><th>Hết hạn</th><th>Hành động</th></tr>
  {% for k in keys %}
  <tr>
    <td><code class="key">{{ k.key }}</code></td>
    <td>{{ k.owner }}</td>
    <td class="{{ 'on' if k.active else 'off' }}">{{ 'ON' if k.active else 'OFF' }}</td>
    <td>{{ k.devicesUsed }}/{{ k.maxDevices }}</td>
    <td>{{ k.daysLeft }}d</td>
    <td>{{ k.expiresAtText }}</td>
    <td>
      <form method="POST" action="/web/adddays" style="display:inline">
        <input type="hidden" name="key" value="{{ k.key }}">
        <input name="days" value="7" style="width:50px">
        <button type="submit" class="neutral">+ngày</button>
      </form>
      <form method="POST" action="/web/revoke" style="display:inline">
        <input type="hidden" name="key" value="{{ k.key }}">
        <button type="submit" class="neutral">Thu hồi</button>
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

TREE_BODY = """
<h1>CÂY KEY</h1>
<div class="box">
  <div class="tree">{{ tree_text or 'Chưa có key nào.' }}</div>
</div>
"""

DEVICES_BODY = """
<h1>THIẾT BỊ</h1>
<div class="box"><div class="scroll"><table>
  <tr><th>Device ID</th><th>Key</th><th>IP</th><th>Lần cuối</th><th>Số lần</th></tr>
  {% for d in devices %}
  <tr>
    <td>{{ d.device_id }}</td>
    <td><code class="key">{{ d.key }}</code></td>
    <td>{{ d.ip }}</td>
    <td>{{ d.lastSeenText }}</td>
    <td>{{ d.count }}</td>
  </tr>
  {% endfor %}
</table>
{% if not devices %}<div class="empty">Chưa có thiết bị.</div>{% endif %}
</div></div>
"""

BLOCKS_BODY = """
<h1>BLOCK LIST</h1>
<div class="box"><div class="scroll"><table>
  <tr><th>Loại</th><th>ID</th><th>Key</th><th>Lý do</th><th>Thời gian</th></tr>
  {% for b in blocks %}
  <tr>
    <td>{{ b.type }}</td>
    <td>{{ b.id }}</td>
    <td><code class="key">{{ b.key or '-' }}</code></td>
    <td>{{ b.reason }}</td>
    <td>{{ b.timeText }}</td>
  </tr>
  {% endfor %}
</table>
{% if not blocks %}<div class="empty">Không có mục nào bị block.</div>{% endif %}
</div></div>
"""

CTV_BODY = """
<h1>QUẢN LÝ CTV</h1>
<div class="box">
  <h2>Thêm CTV</h2>
  <form method="POST" action="/web/addctv" class="row">
    <input name="user_id" placeholder="user_id telegram">
    <input name="name" placeholder="tên">
    <input name="max_keys" value="50" placeholder="max keys">
    <input name="max_days" value="30" placeholder="max days">
    <button type="submit">Thêm</button>
  </form>
</div>
<div class="box"><table>
  <tr><th>UserID</th><th>Tên</th><th>Trạng thái</th><th>Đã tạo</th><th>Max</th><th>Hành động</th></tr>
  {% for c in ctv %}
  <tr>
    <td class="ctv">{{ c.user_id }}</td>
    <td>{{ c.name }}</td>
    <td class="{{ 'on' if c.active else 'off' }}">{{ 'ON' if c.active else 'OFF' }}</td>
    <td>{{ c.keys_created }}</td>
    <td>{{ c.max_keys }}</td>
    <td>
      <form method="POST" action="/web/toggle_ctv" style="display:inline">
        <input type="hidden" name="user_id" value="{{ c.user_id }}">
        <button type="submit" class="neutral">{{ 'Tắt' if c.active else 'Bật' }}</button>
      </form>
      <form method="POST" action="/web/removectv" style="display:inline">
        <input type="hidden" name="user_id" value="{{ c.user_id }}">
        <button type="submit" class="danger">Xóa</button>
      </form>
    </td>
  </tr>
  {% endfor %}
</table>
{% if not ctv %}<div class="empty">Chưa có CTV.</div>{% endif %}
</div>
"""

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
  <tr><th>Tài khoản</th><th>Vai trò</th><th>Trạng thái</th><th>Key</th><th>Hành động</th></tr>
  {% for a in accounts %}
  <tr>
    <td class="user">{{ a.username }}</td>
    <td><span class="tag {{ a.role }}">{{ a.role }}</span></td>
    <td class="{{ 'on' if a.active else 'off' }}">{{ 'ON' if a.active else 'OFF' }}</td>
    <td><code class="key">{{ a.key or '-' }}</code></td>
    <td>
      <form method="POST" action="/accounts/toggle" style="display:inline">
        <input type="hidden" name="username" value="{{ a.username }}">
        <button type="submit" class="neutral">{{ 'Tắt' if a.active else 'Bật' }}</button>
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

MY_PANEL_BODY = """
<h1>XIN CHÀO {{ me.username }}</h1>
<div class="box">
  <div>Tài khoản: <b class="user">{{ me.username }}</b></div>
  <div>Vai trò: <span class="tag {{ me.role }}">{{ me.role }}</span></div>
</div>
<div class="box">
  <h2>KEY CỦA BẠN</h2>
  {% if kr %}
    <div class="key"><code>{{ kr.key }}</code></div>
    <div>Chủ: {{ kr.owner }}</div>
    <div>Hết hạn: {{ kr.expiresAtText }}</div>
    <div>Còn lại: {{ kr.daysLeft }} ngày</div>
    <div>Thiết bị: {{ kr.devicesUsed }}/{{ kr.maxDevices }}</div>
  {% else %}
    <div class="empty">Bạn chưa có key.</div>
    <form method="POST" action="/my/getkey"><button type="submit">NHẬN KEY</button></form>
  {% endif %}
</div>
<div class="box">
  <h2>ĐỔI MẬT KHẨU</h2>
  <form method="POST" action="/my/changepw">
    <input name="old_password" type="password" placeholder="mật khẩu cũ">
    <input name="new_password" type="password" placeholder="mật khẩu mới">
    <button type="submit">Đổi mật khẩu</button>
  </form>
  {% if error %}<div class="err">{{ error }}</div>{% endif %}
  {% if success %}<div class="ok">{{ success }}</div>{% endif %}
</div>
"""

API_MANAGER_BODY = """
<h1>QUẢN LÝ API</h1>
<div class="box">
  <h2>Tạo API Key mới</h2>
  <form method="POST" action="/api/create" class="row">
    <input name="name" placeholder="tên client">
    <input name="scopes" placeholder="quyền (verify,info)">
    <input name="rate_limit" value="60" placeholder="rate/phút">
    <button type="submit">Tạo API Key</button>
  </form>
</div>
<div class="box"><div class="scroll"><table>
  <tr><th>Tên</th><th>Preview</th><th>Quyền</th><th>Rate</th><th>Dùng</th><th>Trạng thái</th><th>Hành động</th></tr>
  {% for k in api_keys %}
  <tr>
    <td>{{ k.name }}</td>
    <td><code class="key">{{ k.keyPreview }}</code></td>
    <td>{{ k.scopesText }}</td>
    <td>{{ k.rateLimit }}</td>
    <td>{{ k.usageCount }}</td>
    <td class="{{ 'on' if k.active else 'off' }}">{{ 'ON' if k.active else 'OFF' }}</td>
    <td>
      <form method="POST" action="/api/toggle" style="display:inline">
        <input type="hidden" name="key" value="{{ k.key }}">
        <button type="submit" class="neutral">Đổi</button>
      </form>
      <form method="POST" action="/api/delete" style="display:inline">
        <input type="hidden" name="key" value="{{ k.key }}">
        <button type="submit" class="danger">Xóa</button>
      </form>
    </td>
  </tr>
  {% endfor %}
</table>
{% if not api_keys %}<div class="empty">Chưa có API key.</div>{% endif %}
</div></div>
"""

# ---------------- AUTH ROUTE ----------------

@web_bp.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if not authmod:
        return "Module auth.py không có.", 500
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        try:
            uid, err = authmod.authenticate_account(u, p)
        except Exception:
            uid = None
        if not uid:
            error = "Sai tài khoản hoặc mật khẩu."
        else:
            token = authmod.create_session(uid)
            resp = make_response(redirect(url_for("web.index")))
            resp.set_cookie("session", token, httponly=True,
                            samesite="Lax", max_age=604800)
            return resp
    return render_template_string(LOGIN_PAGE, error=error, prefill="")

@web_bp.route("/register", methods=["GET", "POST"])
def register():
    error = ""
    if not authmod:
        return "Module auth.py không có.", 500
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        p2 = request.form.get("password2", "")
        if p != p2:
            error = "Mật khẩu nhập lại không khớp."
        else:
            ok, result = authmod.register_account(u, p)
            if not ok:
                error = f"Lỗi: {result}"
            else:
                token = authmod.create_session(result)
                resp = make_response(redirect(url_for("web.my_panel")))
                resp.set_cookie("session", token, httponly=True,
                                samesite="Lax", max_age=604800)
                return resp
    return render_template_string(REGISTER_PAGE, error=error)

@web_bp.route("/logout")
def logout():
    token = request.cookies.get("session")
    if authmod:
        try:
            authmod.destroy_session(token)
        except Exception:
            pass
    resp = make_response(redirect(url_for("web.login")))
    resp.set_cookie("session", "", max_age=0)
    return resp

# ---------------- DASHBOARD ----------------

@web_bp.route("/")
def index():
    me = current_user()
    if not me:
        return redirect(url_for("web.login"))
    try:
        logs = fetchall("SELECT time, event, data FROM logs ORDER BY id DESC LIMIT 20")
        logs = [{"time": fmt_time(r["time"]), "event": r["event"], "data": r["data"]}
                for r in logs]
    except Exception:
        logs = []
    body = render_template_string(
        DASHBOARD_BODY, me=me, s=compute_stats(), logs=logs,
        default_days=DEFAULT_DAYS, default_max_devices=DEFAULT_MAX_DEVICES,
    )
    return page("Dashboard", me, body, "dashboard")

@web_bp.route("/keys")
def keys():
    me = current_user()
    if not me:
        return redirect(url_for("web.login"))
    items = []
    try:
        rows = fetchall("SELECT * FROM keys ORDER BY created_at DESC LIMIT 100")
        now = now_ms()
        for r in rows:
            days_left = max(0, int((r["expires_at"] - now) / 86400000))
            dev_row = fetchone("SELECT COUNT(*) AS c FROM devices WHERE key = ?",
                               (r["key"],))
            items.append({
                "key": r["key"], "owner": r["owner"],
                "active": bool(r["active"]),
                "devicesUsed": dev_row["c"] if dev_row else 0,
                "maxDevices": r["max_devices"],
                "daysLeft": days_left,
                "expiresAtText": fmt_time(r["expires_at"]),
            })
    except Exception as e:
        print(f"[WEB] keys lỗi: {e}")
    body = render_template_string(KEYS_BODY, me=me, keys=items)
    return page("Keys", me, body, "keys")

@web_bp.route("/tree")
def tree():
    me = current_user()
    if not me:
        return redirect(url_for("web.login"))
    tree_text = ""
    if keymod:
        try:
            lines = keymod.render_tree_text(keymod.build_tree_view())
            tree_text = "\n".join(lines)
        except Exception:
            pass
    body = render_template_string(TREE_BODY, me=me, tree_text=tree_text)
    return page("Cây Key", me, body, "tree")

@web_bp.route("/devices")
def devices():
    me = current_user()
    if not me:
        return redirect(url_for("web.login"))
    items = []
    try:
        rows = fetchall("SELECT * FROM devices ORDER BY last_seen DESC LIMIT 200")
        for r in rows:
            items.append({
                "device_id": r["device_id"], "key": r["key"], "ip": r["ip"],
                "lastSeenText": fmt_time(r["last_seen"]),
                "count": r["count"],
            })
    except Exception:
        pass
    body = render_template_string(DEVICES_BODY, me=me, devices=items)
    return page("Thiết bị", me, body, "devices")

@web_bp.route("/blocks")
def blocks():
    me = current_user()
    if not me:
        return redirect(url_for("web.login"))
    items = []
    try:
        rows = fetchall("SELECT * FROM blocked ORDER BY time DESC LIMIT 100")
        for r in rows:
            items.append({
                "type": r["type"], "id": r["id"], "key": r["key"],
                "reason": r["reason"], "timeText": fmt_time(r["time"]),
            })
    except Exception:
        pass
    body = render_template_string(BLOCKS_BODY, me=me, blocks=items)
    return page("Block", me, body, "blocks")

@web_bp.route("/ctv")
def ctv_page():
    me = current_user()
    if not me or me["role"] not in ("admin", "ctv"):
        return make_response("Không có quyền.", 403)
    items = []
    try:
        rows = fetchall("SELECT * FROM ctv ORDER BY added_at DESC")
        items = [dict(r) for r in rows]
    except Exception:
        pass
    body = render_template_string(CTV_BODY, me=me, ctv=items)
    return page("CTV", me, body, "ctv")

@web_bp.route("/accounts")
def accounts_page():
    me = current_user()
    if not me or me["role"] != "admin":
        return make_response("Không có quyền.", 403)
    items = []
    try:
        rows = fetchall("SELECT * FROM accounts ORDER BY created_at DESC")
        items = [dict(r) for r in rows]
    except Exception:
        pass
    body = render_template_string(ACCOUNTS_BODY, me=me, accounts=items,
                                  error=request.args.get("error", ""))
    return page("Tài khoản", me, body, "accounts")

@web_bp.route("/logs")
def logs_page():
    me = current_user()
    if not me:
        return redirect(url_for("web.login"))
    n = int(request.args.get("n", 100))
    items = []
    try:
        rows = fetchall("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (n,))
        items = [{"time": fmt_time(r["time"]), "event": r["event"], "data": r["data"]}
                 for r in rows]
    except Exception:
        pass
    body = render_template_string(LOGS_BODY, me=me, logs=items, n=n)
    return page("Log", me, body, "logs")

@web_bp.route("/api")
def api_manager():
    me = current_user()
    if not me or me["role"] != "admin":
        return make_response("Không có quyền.", 403)
    items = []
    if apikey:
        try:
            items = apikey.list_api_keys()
        except Exception:
            pass
    body = render_template_string(API_MANAGER_BODY, me=me, api_keys=items)
    return page("API", me, body, "api")

@web_bp.route("/my")
def my_panel():
    me = current_user()
    if not me:
        return redirect(url_for("web.login"))
    kr = None
    try:
        rec = fetchone("SELECT * FROM accounts WHERE uid = ?", (me["uid"],))
        key = rec["key"] if rec else None
        if key and keymod:
            kr = keymod.get_key_info(key)
    except Exception:
        pass
    body = render_template_string(
        MY_PANEL_BODY, me=me, kr=kr,
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
    )
    return page("Cá nhân", me, body, "my")

# ---------------- WEB ACTIONS ----------------

@web_bp.route("/web/create", methods=["POST"])
@require_login("write")
def web_create():
    if not keymod:
        return redirect(request.referrer or url_for("web.index"))
    days = int(request.form.get("days", 30))
    owner = request.form.get("owner", "unknown")
    max_dev = int(request.form.get("max_devices", 1))
    try:
        keymod.create_key(days, owner, max_dev)
    except Exception as e:
        print(f"[WEB] create lỗi: {e}")
    return redirect(request.referrer or url_for("web.index"))

@web_bp.route("/web/issue", methods=["POST"])
@require_login("issue")
def web_issue():
    if not keymod:
        return redirect(request.referrer or url_for("web.index"))
    user_id = request.form.get("user_id", "").strip()
    if not user_id:
        return redirect(request.referrer or url_for("web.index"))
    days = int(request.form.get("days", DEFAULT_DAYS))
    max_dev = int(request.form.get("max_devices", DEFAULT_MAX_DEVICES))
    try:
        keymod.create_key(days, f"user_{user_id}", max_dev, user_id=user_id)
    except Exception as e:
        print(f"[WEB] issue lỗi: {e}")
    return redirect(request.referrer or url_for("web.index"))

@web_bp.route("/web/adddays", methods=["POST"])
@require_login("write")
def web_adddays():
    if keymod:
        try:
            keymod.add_days(request.form.get("key", ""),
                            int(request.form.get("days", 0)))
        except Exception:
            pass
    return redirect(request.referrer or url_for("web.keys"))

@web_bp.route("/web/revoke", methods=["POST"])
@require_login("write")
def web_revoke():
    if keymod:
        try:
            keymod.revoke_key(request.form.get("key", ""))
        except Exception:
            pass
    return redirect(request.referrer or url_for("web.keys"))

@web_bp.route("/web/delete", methods=["POST"])
@require_login("delete")
def web_delete():
    if keymod:
        try:
            keymod.delete_key(request.form.get("key", ""))
        except Exception:
            pass
    return redirect(request.referrer or url_for("web.keys"))

@web_bp.route("/web/addctv", methods=["POST"])
@require_login("ctv")
def web_addctv():
    user_id = request.form.get("user_id", "").strip()
    if not user_id:
        return redirect(url_for("web.ctv_page"))
    try:
        insert_or_ignore = None
        from db import insert_or_ignore as ioi
        ioi("ctv", {
            "user_id": user_id,
            "name": request.form.get("name", "") or f"ctv_{user_id}",
            "max_keys": int(request.form.get("max_keys", 50)),
            "max_days": int(request.form.get("max_days", 30)),
            "keys_created": 0,
            "added_at": now_ms(),
            "active": 1,
        })
    except Exception as e:
        print(f"[WEB] addctv lỗi: {e}")
    return redirect(url_for("web.ctv_page"))

@web_bp.route("/web/removectv", methods=["POST"])
@require_login("ctv")
def web_removectv():
    try:
        execute("DELETE FROM ctv WHERE user_id = ?",
                (request.form.get("user_id", ""),))
    except Exception:
        pass
    return redirect(url_for("web.ctv_page"))

@web_bp.route("/web/toggle_ctv", methods=["POST"])
@require_login("ctv")
def web_toggle_ctv():
    try:
        execute("UPDATE ctv SET active = 1 - active WHERE user_id = ?",
                (request.form.get("user_id", ""),))
    except Exception:
        pass
    return redirect(url_for("web.ctv_page"))

@web_bp.route("/accounts/create", methods=["POST"])
@require_login("admin")
def accounts_create():
    if not authmod:
        return redirect(url_for("web.accounts_page"))
    u = request.form.get("username", "").strip()
    p = request.form.get("password", "")
    ok, err = authmod.register_account(u, p)
    if ok:
        uid, _ = authmod.find_account_by_username(u)
        if uid:
            authmod.set_account_role(uid, request.form.get("role", "viewer"))
        return redirect(url_for("web.accounts_page"))
    return redirect(url_for("web.accounts_page", error=err))

@web_bp.route("/accounts/remove", methods=["POST"])
@require_login("admin")
def accounts_remove():
    if not authmod:
        return redirect(url_for("web.accounts_page"))
    u = request.form.get("username", "")
    uid, _ = authmod.find_account_by_username(u)
    me = current_user()
    if uid and me and u != me["username"]:
        authmod.delete_account(uid)
    return redirect(url_for("web.accounts_page"))

@web_bp.route("/accounts/toggle", methods=["POST"])
@require_login("admin")
def accounts_toggle():
    if not authmod:
        return redirect(url_for("web.accounts_page"))
    uid, _ = authmod.find_account_by_username(request.form.get("username", ""))
    if uid:
        authmod.toggle_account(uid)
    return redirect(url_for("web.accounts_page"))

@web_bp.route("/api/create", methods=["POST"])
@require_login("admin")
def api_create():
    if apikey:
        try:
            apikey.create_api_key(
                request.form.get("name", "client"),
                request.form.get("scopes", "verify,info").split(","),
                "client",
                int(request.form.get("rate_limit", 60)),
            )
        except Exception:
            pass
    return redirect(url_for("web.api_manager"))

@web_bp.route("/api/toggle", methods=["POST"])
@require_login("admin")
def api_toggle():
    if apikey:
        try:
            apikey.toggle_api_key(request.form.get("key", ""))
        except Exception:
            pass
    return redirect(url_for("web.api_manager"))

@web_bp.route("/api/delete", methods=["POST"])
@require_login("admin")
def api_delete():
    if apikey:
        try:
            apikey.delete_api_key(request.form.get("key", ""))
        except Exception:
            pass
    return redirect(url_for("web.api_manager"))

@web_bp.route("/my/getkey", methods=["POST"])
def my_getkey():
    me = current_user()
    if not me or not keymod:
        return redirect(url_for("web.login"))
    try:
        keymod.create_key(DEFAULT_DAYS, me["username"], DEFAULT_MAX_DEVICES,
                          user_id=me["uid"])
    except Exception:
        pass
    return redirect(url_for("web.my_panel"))

@web_bp.route("/my/changepw", methods=["POST"])
def my_changepw():
    me = current_user()
    if not me or not authmod:
        return redirect(url_for("web.login"))
    try:
        ok, err = authmod.change_account_password(
            me["uid"],
            request.form.get("old_password", ""),
            request.form.get("new_password", ""),
        )
    except Exception:
        ok, err = False, "error"
    if not ok:
        return redirect(url_for("web.my_panel", error=str(err)))
    return redirect(url_for("web.my_panel", success="Đã đổi mật khẩu."))

# ---------------- ĐĂNG KÝ ----------------

def register(app):
    """Đăng ký blueprint vào Flask app."""
    app.register_blueprint(web_bp)
    return web_bp
