# ============================================================
# FILE: web.py - NÂNG CẤP TOÀN DIỆN
# MÔ TẢ: Flask Blueprint với bảo mật, tối ưu, UI v2, audit log
# ============================================================

import os
import json
import time
import html
import secrets
import hashlib
import threading
from functools import wraps
from datetime import datetime

from flask import (
    Blueprint, request, jsonify, render_template_string,
    make_response, redirect, url_for, abort, g, current_app,
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
    def fetchone(*a, **k): return None
    def fetchall(*a, **k): return []
    def execute(*a, **k): return None

# ---------------- CẤU HÌNH ----------------

DEFAULT_DAYS = 30
DEFAULT_MAX_DEVICES = 1
if keymod:
    DEFAULT_DAYS = getattr(keymod, "DEFAULT_DAYS", 30)
    DEFAULT_MAX_DEVICES = getattr(keymod, "DEFAULT_MAX_DEVICES", 1)

CTV_MAX_DAYS = int(os.environ.get("CTV_MAX_DAYS", "30"))
CTV_MAX_KEYS = int(os.environ.get("CTV_MAX_KEYS", "50"))
PER_PAGE = int(os.environ.get("WEB_PER_PAGE", "25"))
CSRF_ENABLED = os.environ.get("CSRF_ENABLED", "true").lower() == "true"
SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "true").lower() == "true"
RATE_LIMIT_LOGIN = int(os.environ.get("RATE_LIMIT_LOGIN", "5"))
RATE_LIMIT_DEFAULT = int(os.environ.get("RATE_LIMIT_DEFAULT", "120"))

web_bp = Blueprint("web", __name__)

# ============================================================
# RATE LIMIT (IN-MEMORY)
# ============================================================

_rl_store = {}
_rl_lock = threading.Lock()

def rate_limit(key, limit=RATE_LIMIT_DEFAULT, window=60):
    now = time.time()
    with _rl_lock:
        bucket = _rl_store.setdefault(key, [])
        bucket[:] = [t for t in bucket if now - t < window]
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

def _client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"

# ============================================================
# CSRF
# ============================================================

def _csrf_secret():
    s = os.environ.get("CSRF_SECRET")
    if not s:
        s = hashlib.sha256(
            (os.environ.get("BOT_TOKEN", "x") + "csrf").encode()
        ).hexdigest()
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
    expect = hashlib.sha256(
        (_csrf_secret() + f"{uid}:{ts}").encode()
    ).hexdigest()[:32]
    return secrets.compare_digest(expect, sig)

# ============================================================
# AUDIT LOG
# ============================================================

def audit(event, data="", uid=None, ip=None):
    try:
        execute(
            "INSERT INTO logs (time, event, data) VALUES (?, ?, ?)",
            (now_ms(), event, f"{uid or '-'}|{ip or '-'}|{data}")[:500])
    except Exception:
        pass

# ============================================================
# CSS V2 - DARK MODERN RESPONSIVE
# ============================================================

BASE_CSS = """
<style>
:root{
  --bg:#0a0e14; --bg2:#0f141b; --panel:#141a22; --panel2:#1a212b;
  --border:#232c38; --border2:#2d3946;
  --fg:#c9d1d9; --fg2:#8b949e; --fg3:#6a737d;
  --accent:#58a6ff; --accent2:#1f6feb;
  --ok:#3fb950; --warn:#d29922; --err:#f85149; --info:#79c0ff;
  --purple:#a371f7; --orange:#f0883e;
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
  min-height:100vh;padding:12px;
}
h1{font-size:20px;color:var(--accent);margin:0 0 8px}
h2{font-size:15px;color:var(--accent);margin:0 0 10px;font-weight:600;
   border-bottom:1px solid var(--border);padding-bottom:6px}
h3{font-size:14px;color:var(--info);margin:0 0 6px}
a{color:var(--accent);text-decoration:none;transition:color .15s}
a:hover{color:var(--info);text-decoration:underline}

/* NAV */
.nav{
  display:flex;gap:6px;flex-wrap:wrap;align-items:center;
  padding:10px 12px;background:rgba(15,20,27,.95);
  border:1px solid var(--border);border-radius:var(--radius2);
  margin-bottom:14px;font-size:13px;
  position:sticky;top:0;z-index:50;
  backdrop-filter:blur(8px);
}
.nav a{
  padding:5px 10px;border-radius:6px;background:var(--panel2);
  color:var(--fg2);transition:all .15s;
}
.nav a:hover{background:var(--border2);color:var(--fg);text-decoration:none}
.nav a.active{background:var(--accent2);color:#fff}
.nav .brand{color:var(--accent);font-weight:700;padding:4px 8px;background:var(--panel)}

/* BOX */
.box{
  border:1px solid var(--border);padding:16px;margin:0 0 14px;
  border-radius:var(--radius2);background:var(--panel);
  box-shadow:var(--shadow);
}
.box.tight{padding:12px}

/* GRID */
.grid{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.grid-2{display:grid;gap:10px;grid-template-columns:1fr 1fr}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:flex-start}
.row > *{flex:1;min-width:120px}
.row.tight > *{min-width:0}

/* STAT */
.stat{
  border:1px solid var(--border);padding:12px;border-radius:var(--radius);
  background:var(--bg2);transition:border-color .15s;
}
.stat:hover{border-color:var(--border2)}
.stat b{color:var(--accent);font-size:22px;display:block;margin-top:4px;font-weight:700}
.stat.ok b{color:var(--ok)}
.stat.warn b{color:var(--warn)}
.stat.err b{color:var(--err)}
.stat .lbl{color:var(--fg2);font-size:11px;text-transform:uppercase;letter-spacing:.5px}

/* FORM */
input,button,select,textarea{
  background:var(--bg2);color:var(--fg);
  border:1px solid var(--border2);
  padding:10px 12px;border-radius:var(--radius);
  font-family:inherit;font-size:13px;width:100%;margin:3px 0;
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

/* TABLE */
table{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}
th,td{border-bottom:1px solid var(--border);padding:9px 8px;
      text-align:left;vertical-align:top;word-break:break-all}
th{background:var(--bg2);color:var(--accent);font-weight:600;
   text-transform:uppercase;font-size:11px;letter-spacing:.5px}
tr:hover td{background:rgba(88,166,255,.04)}
td code{background:var(--bg2);padding:2px 6px;border-radius:4px;
        color:var(--ok);font-size:11px}

/* TAG */
.tag{display:inline-block;padding:2px 8px;border-radius:20px;
     font-size:11px;font-weight:600;background:var(--panel2);color:var(--fg2)}
.tag.admin{background:rgba(240,136,62,.15);color:var(--orange);border:1px solid rgba(240,136,62,.3)}
.tag.ctv{background:rgba(163,113,247,.15);color:var(--purple);border:1px solid rgba(163,113,247,.3)}
.tag.user{background:rgba(63,185,80,.15);color:var(--ok);border:1px solid rgba(63,185,80,.3)}
.tag.viewer{background:var(--panel2);color:var(--fg2)}
.tag.on{background:rgba(63,185,80,.15);color:var(--ok)}
.tag.off{background:rgba(248,81,73,.15);color:var(--err)}

.on{color:var(--ok)} .off{color:var(--err)} .blk{color:var(--warn)}
.user{color:var(--purple)} .ctv{color:var(--orange)}
.key{color:var(--ok);word-break:break-all;font-size:12px}

/* TREE */
.tree{
  font-size:12px;line-height:1.6;white-space:pre;overflow-x:auto;
  padding:12px;background:#010409;border:1px solid var(--border);
  border-radius:var(--radius);color:var(--ok);
}

/* ALERT */
.err{color:var(--err);font-size:12px;min-height:14px;margin-top:6px}
.ok{color:var(--ok);font-size:12px;margin-top:6px}
.alert{padding:10px 12px;border-radius:var(--radius);font-size:12px;
       margin-top:8px;border-left:3px solid}
.alert.err{background:rgba(248,81,73,.08);color:var(--err);border-color:var(--err)}
.alert.ok{background:rgba(63,185,80,.08);color:var(--ok);border-color:var(--ok)}
.alert.warn{background:rgba(210,153,34,.08);color:var(--warn);border-color:var(--warn)}
.alert.info{background:rgba(121,192,255,.08);color:var(--info);border-color:var(--info)}

.scroll{max-height:520px;overflow-y:auto;border-radius:var(--radius)}
.empty{color:var(--fg2);font-style:italic;padding:14px;text-align:center}

/* PAGINATION */
.pager{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px;align-items:center}
.pager a{padding:5px 10px;border-radius:6px;background:var(--panel2);
         color:var(--fg2);font-size:12px}
.pager a:hover{background:var(--border2);color:var(--fg)}
.pager a.active{background:var(--accent2);color:#fff}
.pager .info{color:var(--fg3);font-size:11px;margin-left:auto}

/* TOAST */
.toast{
  position:fixed;bottom:20px;right:20px;z-index:100;
  background:var(--panel);border:1px solid var(--border2);
  padding:12px 16px;border-radius:var(--radius);
  box-shadow:var(--shadow);max-width:340px;
  animation:slideIn .3s ease-out;
}
.toast.ok{border-left:3px solid var(--ok)}
.toast.err{border-left:3px solid var(--err)}
@keyframes slideIn{from{transform:translateX(120%)}to{transform:translateX(0)}}

/* WRAP */
.wrap{max-width:440px;margin:60px auto;padding:0 12px}
.center{text-align:center}
.muted{color:var(--fg2);font-size:12px}
.tiny{font-size:11px;color:var(--fg3)}
.mt{margin-top:12px}.mb{margin-bottom:12px}

/* RESPONSIVE */
@media(max-width:640px){
  body{padding:8px}
  .nav{padding:8px;font-size:12px}
  .nav a{padding:4px 8px;font-size:11px}
  .box{padding:12px}
  .stat b{font-size:18px}
  h1{font-size:17px}
  .wrap{margin:20px auto}
  .grid-2{grid-template-columns:1fr}
  th,td{padding:6px 4px;font-size:11px}
}
</style>
"""

# ============================================================
# HTML HELPERS
# ============================================================

def _esc(t):
    if t is None: return ""
    return html.escape(str(t), quote=False)

def _toast(msg, kind="ok"):
    if not msg: return ""
    return f'<div class="toast {kind}">{_esc(msg)}</div>'

# ============================================================
# LAYOUT
# ============================================================

def nav_html(me, active=""):
    if me and me.get("role") == "admin":
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
    elif me:
        items = [
            ("/", "Dashboard", "dashboard"),
            ("/keys", "Keys", "keys"),
            ("/my", "Cá nhân", "my"),
        ]
    else:
        items = []
    links = ""
    for url, label, name in items:
        cls = 'navlink active' if name == active else 'navlink'
        links += f'<a class="{cls}" href="{url}">{label}</a>'
    if me:
        role_cls = me.get("role", "user")
        me_tag = (f'<span class="tag {role_cls}">{_esc(me["username"])}</span>'
                  f'<a href="/logout">Thoát</a>')
    else:
        me_tag = '<a href="/login">Đăng nhập</a>'
    return (f'<div class="nav"><span class="brand">🔑 KEY SERVER</span>'
            f'{links}<span style="flex:1"></span>{me_tag}</div>')

def page(title, me, body, active=""):
    return (f'<!DOCTYPE html><html lang="vi"><head>'
            f'<meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow">'
            f'<meta name="theme-color" content="#0a0e14">'
            f'<title>{_esc(title)} · KEY SERVER</title>'
            f'{BASE_CSS}</head><body>'
            f'{nav_html(me, active)}{body}</body></html>')

# ============================================================
# AUTH
# ============================================================

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
        return {
            "uid": s["uid"],
            "username": rec["username"],
            "role": rec.get("role", "user"),
            "csrf": make_csrf(s["uid"]),
        }
    except Exception:
        return None

def require_login(perm=None):
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            me = current_user()
            if not me:
                return redirect(url_for("web.login",
                                        next=request.path))
            if perm and authmod:
                try:
                    if not authmod.has_permission(me["role"], perm):
                        abort(403)
                except Exception:
                    abort(403)
            g.me = me
            return f(*args, **kwargs)
        return wrapper
    return deco

def verify_csrf():
    if not CSRF_ENABLED:
        return True
    me = current_user()
    if not me:
        return False
    return check_csrf(me["uid"], request.form.get("csrf", ""))

def csrf_field(me):
    return f'<input type="hidden" name="csrf" value="{me["csrf"]}">'

# ============================================================
# STATS
# ============================================================

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
        return dict(row) if row else {}
    except Exception:
        return {}

# ============================================================
# TEMPLATES
# ============================================================

LOGIN_PAGE = """<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Đăng nhập · KEY SERVER</title>""" + BASE_CSS + """</head><body>
<div class="wrap"><div class="box">
  <h1>🔑 ĐĂNG NHẬP</h1>
  <p class="muted mb">Nhập thông tin tài khoản để tiếp tục.</p>
  <form method="POST" action="/login">
    <input name="username" placeholder="tài khoản" value="{{ prefill or '' }}" required autocomplete="username">
    <input name="password" type="password" placeholder="mật khẩu" required autocomplete="current-password">
    {% if error %}<div class="alert err">{{ error }}</div>{% endif %}
    <button type="submit" class="mt">Đăng nhập</button>
  </form>
  <div class="center mt muted">Chưa có tài khoản? <a href="/register">Đăng ký</a></div>
</div></div></body></html>"""

REGISTER_PAGE = """<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Đăng ký · KEY SERVER</title>""" + BASE_CSS + """</head><body>
<div class="wrap"><div class="box">
  <h1>🔑 ĐĂNG KÝ</h1>
  <p class="muted mb">Tạo tài khoản mới để nhận key.</p>
  <form method="POST" action="/register">
    <input name="username" placeholder="tài khoản (≥3 ký tự)" required>
    <input name="password" type="password" placeholder="mật khẩu (≥6 ký tự)" required>
    <input name="password2" type="password" placeholder="nhập lại mật khẩu" required>
    {% if error %}<div class="alert err">{{ error }}</div>{% endif %}
    <button type="submit" class="mt">Đăng ký</button>
  </form>
  <div class="center mt muted">Đã có tài khoản? <a href="/login">Đăng nhập</a></div>
</div></div></body></html>"""

DASHBOARD_BODY = """
<h1>📊 DASHBOARD</h1>
<div class="grid">
  <div class="stat"><span class="lbl">Tổng key</span><b>{{ s.get('totalKeys',0) }}</b></div>
  <div class="stat ok"><span class="lbl">Hoạt động</span><b>{{ s.get('activeKeys',0) }}</b></div>
  <div class="stat err"><span class="lbl">Hết hạn</span><b>{{ s.get('expiredKeys',0) }}</b></div>
  <div class="stat"><span class="lbl">Thiết bị</span><b>{{ s.get('totalDevices',0) }}</b></div>
  <div class="stat"><span class="lbl">Tài khoản</span><b>{{ s.get('totalUsers',0) }}</b></div>
  <div class="stat warn"><span class="lbl">CTV</span><b>{{ s.get('totalCtv',0) }}</b></div>
  <div class="stat warn"><span class="lbl">Block key</span><b>{{ s.get('blockedKeys',0) }}</b></div>
  <div class="stat warn"><span class="lbl">Block TB</span><b>{{ s.get('blockedDevices',0) }}</b></div>
</div>

<div class="grid-2">
  <div class="box">
    <h2>➕ TẠO KEY MỚI</h2>
    <form method="POST" action="/web/create" class="row">
      <input type="hidden" name="csrf" value="{{ me.csrf }}">
      <input name="days" value="30" placeholder="số ngày" type="number" min="1">
      <input name="owner" placeholder="chủ sở hữu">
      <input name="max_devices" value="1" placeholder="max TB" type="number" min="1">
      <button type="submit">Tạo key</button>
    </form>
  </div>
  <div class="box">
    <h2>🎫 CẤP KEY THEO USER</h2>
    <form method="POST" action="/web/issue" class="row">
      <input type="hidden" name="csrf" value="{{ me.csrf }}">
      <input name="user_id" placeholder="user_id telegram">
      <input name="days" value="{{ default_days }}" placeholder="số ngày" type="number" min="1">
      <input name="max_devices" value="{{ default_max_devices }}" placeholder="max TB" type="number" min="1">
      <button type="submit">Cấp key</button>
    </form>
  </div>
</div>

<div class="box">
  <h2>📜 LOG GẦN ĐÂY</h2>
  <div class="scroll"><table>
    <tr><th>Thời gian</th><th>Sự kiện</th><th>Dữ liệu</th></tr>
    {% for l in logs %}
    <tr><td class="tiny">{{ l.time }}</td><td>{{ l.event }}</td><td class="tiny">{{ l.data }}</td></tr>
    {% endfor %}
  </table>
  {% if not logs %}<div class="empty">Chưa có log.</div>{% endif %}
  </div>
</div>
"""

KEYS_BODY = """
<h1>📋 DANH SÁCH KEY</h1>
<div class="box">
  <form method="POST" action="/web/create" class="row tight">
    <input type="hidden" name="csrf" value="{{ me.csrf }}">
    <input name="days" value="30" placeholder="số ngày" type="number" min="1">
    <input name="owner" placeholder="chủ sở hữu">
    <input name="max_devices" value="1" placeholder="max TB" type="number" min="1">
    <button type="submit" class="small">➕ Tạo</button>
  </form>
</div>
<div class="box">
  <form method="GET" action="/keys" class="row tight mb">
    <input name="q" value="{{ q }}" placeholder="Tìm key hoặc chủ...">
    <select name="status">
      <option value="all" {{ 'selected' if status=='all' }}>Tất cả</option>
      <option value="active" {{ 'selected' if status=='active' }}>Hoạt động</option>
      <option value="expired" {{ 'selected' if status=='expired' }}>Hết hạn</option>
      <option value="inactive" {{ 'selected' if status=='inactive' }}>Đã tắt</option>
    </select>
    <button type="submit" class="small neutral">🔍 Lọc</button>
  </form>
  <div class="scroll"><table>
  <tr><th>Key</th><th>Chủ</th><th>Trạng thái</th><th>TB</th><th>Còn</th><th>Hết hạn</th><th>Hành động</th></tr>
  {% for k in keys %}
  <tr>
    <td><code class="key">{{ k.key[:24] }}{% if k.key|length > 24 %}…{% endif %}</code></td>
    <td>{{ k.owner }}</td>
    <td><span class="tag {{ 'on' if k.active else 'off' }}">{{ 'ON' if k.active else 'OFF' }}</span></td>
    <td>{{ k.devicesUsed }}/{{ k.maxDevices }}</td>
    <td>{{ k.daysLeft }}d</td>
    <td class="tiny">{{ k.expiresAtText }}</td>
    <td>
      <form method="POST" action="/web/adddays" style="display:inline">
        <input type="hidden" name="csrf" value="{{ me.csrf }}">
        <input type="hidden" name="key" value="{{ k.key }}">
        <input name="days" value="7" style="width:48px;padding:4px" type="number">
        <button type="submit" class="neutral small">+ngày</button>
      </form>
      <form method="POST" action="/web/revoke" style="display:inline">
        <input type="hidden" name="csrf" value="{{ me.csrf }}">
        <input type="hidden" name="key" value="{{ k.key }}">
        <button type="submit" class="neutral small">Thu hồi</button>
      </form>
      <form method="POST" action="/web/delete" style="display:inline"
            onsubmit="return confirm('Xóa key này?')">
        <input type="hidden" name="csrf" value="{{ me.csrf }}">
        <input type="hidden" name="key" value="{{ k.key }}">
        <button type="submit" class="danger small">Xóa</button>
      </form>
    </td>
  </tr>
  {% endfor %}
  </table>
  {% if not keys %}<div class="empty">Chưa có key nào.</div>{% endif %}
  </div>
  {% if total_pages > 1 %}
  <div class="pager">
    {% for p in page_range %}
      <a href="?q={{ q }}&status={{ status }}&page={{ p }}"
         class="{{ 'active' if p==page else '' }}">{{ p }}</a>
    {% endfor %}
    <span class="info">Trang {{ page }}/{{ total_pages }} · {{ total }} key</span>
  </div>
  {% endif %}
</div>
"""

TREE_BODY = """
<h1>🌳 CÂY KEY</h1>
<div class="box">
  <div class="tree">{{ tree_text or 'Chưa có key nào.' }}</div>
</div>
"""

DEVICES_BODY = """
<h1>💻 THIẾT BỊ</h1>
<div class="box"><div class="scroll"><table>
  <tr><th>Device ID</th><th>Key</th><th>IP</th><th>Lần cuối</th><th>Số lần</th></tr>
  {% for d in devices %}
  <tr>
    <td class="tiny">{{ d.device_id }}</td>
    <td><code class="key">{{ d.key[:20] }}{% if d.key|length > 20 %}…{% endif %}</code></td>
    <td class="tiny">{{ d.ip }}</td>
    <td class="tiny">{{ d.lastSeenText }}</td>
    <td>{{ d.count }}</td>
  </tr>
  {% endfor %}
</table>
{% if not devices %}<div class="empty">Chưa có thiết bị.</div>{% endif %}
</div></div>
"""

BLOCKS_BODY = """
<h1>🚫 BLOCK LIST</h1>
<div class="box"><div class="scroll"><table>
  <tr><th>Loại</th><th>ID</th><th>Key</th><th>Lý do</th><th>Thời gian</th></tr>
  {% for b in blocks %}
  <tr>
    <td><span class="tag off">{{ b.type }}</span></td>
    <td class="tiny">{{ b.id }}</td>
    <td><code class="key">{{ (b.key or '-')[:20] }}</code></td>
    <td>{{ b.reason }}</td>
    <td class="tiny">{{ b.timeText }}</td>
  </tr>
  {% endfor %}
</table>
{% if not blocks %}<div class="empty">Không có mục nào bị block.</div>{% endif %}
</div></div>
"""

CTV_BODY = """
<h1>🤝 QUẢN LÝ CTV</h1>
<div class="box">
  <h2>➕ THÊM CTV</h2>
  <form method="POST" action="/web/addctv" class="row">
    <input type="hidden" name="csrf" value="{{ me.csrf }}">
    <input name="user_id" placeholder="user_id telegram" required>
    <input name="name" placeholder="tên">
    <input name="max_keys" value="{{ ctv_max_keys }}" placeholder="max keys" type="number">
    <input name="max_days" value="{{ ctv_max_days }}" placeholder="max days" type="number">
    <button type="submit">Thêm</button>
  </form>
</div>
<div class="box"><table>
  <tr><th>UserID</th><th>Tên</th><th>Trạng thái</th><th>Đã tạo</th><th>Max</th><th>Hành động</th></tr>
  {% for c in ctv %}
  <tr>
    <td class="ctv">{{ c.user_id }}</td>
    <td>{{ c.name }}</td>
    <td><span class="tag {{ 'on' if c.active else 'off' }}">{{ 'ON' if c.active else 'OFF' }}</span></td>
    <td>{{ c.keys_created }}</td>
    <td>{{ c.max_keys }}</td>
    <td>
      <form method="POST" action="/web/toggle_ctv" style="display:inline">
        <input type="hidden" name="csrf" value="{{ me.csrf }}">
        <input type="hidden" name="user_id" value="{{ c.user_id }}">
        <button type="submit" class="neutral small">{{ 'Tắt' if c.active else 'Bật' }}</button>
      </form>
      <form method="POST" action="/web/removectv" style="display:inline"
            onsubmit="return confirm('Xóa CTV này?')">
        <input type="hidden" name="csrf" value="{{ me.csrf }}">
        <input type="hidden" name="user_id" value="{{ c.user_id }}">
        <button type="submit" class="danger small">Xóa</button>
      </form>
    </td>
  </tr>
  {% endfor %}
</table>
{% if not ctv %}<div class="empty">Chưa có CTV.</div>{% endif %}
</div>
"""

ACCOUNTS_BODY = """
<h1>👥 QUẢN LÝ TÀI KHOẢN</h1>
<div class="box">
  <h2>➕ TẠO TÀI KHOẢN</h2>
  <form method="POST" action="/accounts/create" class="row">
    <input type="hidden" name="csrf" value="{{ me.csrf }}">
    <input name="username" placeholder="tài khoản" required>
    <input name="password" type="password" placeholder="mật khẩu" required>
    <select name="role">
      <option value="admin">admin</option>
      <option value="operator">operator</option>
      <option value="ctv">ctv</option>
      <option value="viewer" selected>viewer</option>
    </select>
    <button type="submit">Tạo</button>
  </form>
  {% if error %}<div class="alert err">{{ error }}</div>{% endif %}
</div>
<div class="box"><div class="scroll"><table>
  <tr><th>Tài khoản</th><th>Vai trò</th><th>Trạng thái</th><th>Key</th><th>Hành động</th></tr>
  {% for a in accounts %}
  <tr>
    <td class="user">{{ a.username }}</td>
    <td><span class="tag {{ a.role }}">{{ a.role }}</span></td>
    <td><span class="tag {{ 'on' if a.active else 'off' }}">{{ 'ON' if a.active else 'OFF' }}</span></td>
    <td><code class="key">{{ (a.key or '-')[:20] }}</code></td>
    <td>
      <form method="POST" action="/accounts/toggle" style="display:inline">
        <input type="hidden" name="csrf" value="{{ me.csrf }}">
        <input type="hidden" name="username" value="{{ a.username }}">
        <button type="submit" class="neutral small">{{ 'Tắt' if a.active else 'Bật' }}</button>
      </form>
      <form method="POST" action="/accounts/remove" style="display:inline"
            onsubmit="return confirm('Xóa tài khoản này?')">
        <input type="hidden" name="csrf" value="{{ me.csrf }}">
        <input type="hidden" name="username" value="{{ a.username }}">
        <button type="submit" class="danger small">Xóa</button>
      </form>
    </td>
  </tr>
  {% endfor %}
</table></div>
"""

LOGS_BODY = """
<h1>📜 LOG HỆ THỐNG</h1>
<div class="box">
  <form method="GET" action="/logs" class="row tight">
    <input name="n" value="{{ n }}" placeholder="số dòng" type="number" min="10" max="1000">
    <button type="submit" class="neutral small">Xem</button>
  </form>
</div>
<div class="box"><div class="scroll"><table>
  <tr><th>Thời gian</th><th>Sự kiện</th><th>Dữ liệu</th></tr>
  {% for l in logs %}
  <tr><td class="tiny">{{ l.time }}</td><td>{{ l.event }}</td><td class="tiny">{{ l.data }}</td></tr>
  {% endfor %}
</table>
{% if not logs %}<div class="empty">Chưa có log.</div>{% endif %}
</div></div>
"""

MY_PANEL_BODY = """
<h1>👋 XIN CHÀO {{ me.username }}</h1>
<div class="box">
  <p>Vai trò: <span class="tag {{ me.role }}">{{ me.role }}</span>
  · UID: <code>{{ me.uid }}</code></p>
</div>
<div class="box">
  <h2>🔑 KEY CỦA BẠN</h2>
  {% if kr %}
    <div class="tree">{{ kr.key }}</div>
    <div class="grid mt">
      <div class="stat"><span class="lbl">Chủ</span><b style="font-size:14px">{{ kr.owner }}</b></div>
      <div class="stat {{ 'ok' if kr.daysLeft > 7 else 'warn' }}"><span class="lbl">Còn lại</span><b>{{ kr.daysLeft }} ngày</b></div>
      <div class="stat"><span class="lbl">Thiết bị</span><b>{{ kr.devicesUsed }}/{{ kr.maxDevices }}</b></div>
      <div class="stat"><span class="lbl">Hết hạn</span><b style="font-size:12px">{{ kr.expiresAtText }}</b></div>
    </div>
    <button class="neutral small mt" onclick="navigator.clipboard.writeText('{{ kr.key }}')">📋 Copy key</button>
  {% else %}
    <div class="empty">Bạn chưa có key.</div>
    <form method="POST" action="/my/getkey" class="mt">
      <input type="hidden" name="csrf" value="{{ me.csrf }}">
      <button type="submit">🎁 NHẬN KEY</button>
    </form>
  {% endif %}
</div>
<div class="grid-2">
  <div class="box">
    <h2>🔒 ĐỔI MẬT KHẨU</h2>
    <form method="POST" action="/my/changepw">
      <input type="hidden" name="csrf" value="{{ me.csrf }}">
      <input name="old_password" type="password" placeholder="mật khẩu cũ" required>
      <input name="new_password" type="password" placeholder="mật khẩu mới (≥6)" required>
      <button type="submit" class="mt">Đổi mật khẩu</button>
    </form>
  </div>
  <div class="box">
    <h2>⚡ THAO TÁC</h2>
    <div class="row tight">
      <a href="/keys"><button class="neutral small">📋 Keys</button></a>
      <a href="/"><button class="neutral small">📊 Dashboard</button></a>
    </div>
    {% if kr %}
    <form method="POST" action="/my/revoke" class="mt"
          onsubmit="return confirm('Thu hồi key hiện tại?')">
      <input type="hidden" name="csrf" value="{{ me.csrf }}">
      <button type="submit" class="danger small">🗑 Thu hồi key</button>
    </form>
    {% endif %}
  </div>
</div>
{{ toast|safe }}
"""

API_MANAGER_BODY = """
<h1>🔐 QUẢN LÝ API KEY</h1>
<div class="box">
  <h2>➕ TẠO API KEY</h2>
  <form method="POST" action="/api/create" class="row">
    <input type="hidden" name="csrf" value="{{ me.csrf }}">
    <input name="name" placeholder="tên client" required>
    <input name="scopes" value="verify,info" placeholder="quyền (csv)">
    <input name="rate_limit" value="60" placeholder="rate/phút" type="number">
    <button type="submit">Tạo API Key</button>
  </form>
</div>
<div class="box"><div class="scroll"><table>
  <tr><th>Tên</th><th>Preview</th><th>Quyền</th><th>Rate</th><th>Dùng</th><th>Trạng thái</th><th>Hành động</th></tr>
  {% for k in api_keys %}
  <tr>
    <td>{{ k.name }}</td>
    <td><code class="key">{{ k.keyPreview }}</code></td>
    <td class="tiny">{{ k.scopesText }}</td>
    <td>{{ k.rateLimit }}</td>
    <td>{{ k.usageCount }}</td>
    <td><span class="tag {{ 'on' if k.active else 'off' }}">{{ 'ON' if k.active else 'OFF' }}</span></td>
    <td>
      <form method="POST" action="/api/toggle" style="display:inline">
        <input type="hidden" name="csrf" value="{{ me.csrf }}">
        <input type="hidden" name="key" value="{{ k.key }}">
        <button type="submit" class="neutral small">Đổi</button>
      </form>
      <form method="POST" action="/api/delete" style="display:inline"
            onsubmit="return confirm('Xóa API key này?')">
        <input type="hidden" name="csrf" value="{{ me.csrf }}">
        <input type="hidden" name="key" value="{{ k.key }}">
        <button type="submit" class="danger small">Xóa</button>
      </form>
    </td>
  </tr>
  {% endfor %}
</table>
{% if not api_keys %}<div class="empty">Chưa có API key.</div>{% endif %}
</div></div>
"""

# ============================================================
# ERROR HANDLERS
# ============================================================

@web_bp.app_errorhandler(403)
def _403(e):
    me = current_user()
    body = """
    <div class="wrap"><div class="box center">
    <h1>403</h1><p class="muted">Không có quyền truy cập.</p>
    <div class="mt"><a href="/"><button class="neutral">← Về Dashboard</button></a></div>
    </div></div>"""
    return page("403", me, body), 403

@web_bp.app_errorhandler(404)
def _404(e):
    me = current_user()
    body = """
    <div class="wrap"><div class="box center">
    <h1>404</h1><p class="muted">Không tìm thấy trang.</p>
    <div class="mt"><a href="/"><button class="neutral">← Về Dashboard</button></a></div>
    </div></div>"""
    return page("404", me, body), 404

@web_bp.app_errorhandler(429)
def _429(e):
    return jsonify({"ok": False, "error": "rate_limited"}), 429

# ============================================================
# BEFORE / AFTER REQUEST
# ============================================================

@web_bp.before_app_request
def _rl_global():
    ip = _client_ip()
    path = request.path
    if path.startswith(("/api/verify", "/api/info", "/api/health",
                        "/api/", "/static")):
        return None
    if path in ("/login", "/register"):
        return None
    if not rate_limit(f"ip:{ip}", limit=RATE_LIMIT_DEFAULT, window=60):
        return jsonify({"ok": False, "error": "rate_limited"}), 429
    return None

@web_bp.after_app_request
def _sec_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
    return resp

# ============================================================
# ROUTES: AUTH
# ============================================================

@web_bp.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if not authmod:
        return "Module auth.py không có.", 500
    if request.method == "POST":
        if not rate_limit(f"login:{_client_ip()}", RATE_LIMIT_LOGIN, 60):
            error = "Quá nhiều lần thử. Vui lòng chờ."
        else:
            u = request.form.get("username", "").strip()
            p = request.form.get("password", "")
            uid = None
            try:
                uid, _ = authmod.authenticate_account(u, p)
            except Exception:
                uid = None
            if not uid:
                error = "Sai tài khoản hoặc mật khẩu."
                audit("login_fail", u, ip=_client_ip())
            else:
                token = authmod.create_session(uid)
                nxt = request.args.get("next") or "/"
                if not nxt.startswith("/"):
                    nxt = "/"
                resp = make_response(redirect(nxt))
                resp.set_cookie("session", token, httponly=True,
                                samesite="Lax", secure=SECURE_COOKIES,
                                max_age=604800)
                audit("login_ok", u, uid=uid, ip=_client_ip())
                return resp
    return render_template_string(LOGIN_PAGE, error=error, prefill="")

@web_bp.route("/register", methods=["GET", "POST"])
def register():
    error = ""
    if not authmod:
        return "Module auth.py không có.", 500
    if request.method == "POST":
        if not rate_limit(f"reg:{_client_ip()}", 3, 300):
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
            else:
                try:
                    ok, result = authmod.register_account(u, p)
                except Exception as e:
                    ok, result = False, str(e)
                if not ok:
                    error = f"Lỗi: {result}"
                else:
                    token = authmod.create_session(result)
                    resp = make_response(redirect(url_for("web.my_panel")))
                    resp.set_cookie("session", token, httponly=True,
                                    samesite="Lax", secure=SECURE_COOKIES,
                                    max_age=604800)
                    audit("register_ok", u, uid=result, ip=_client_ip())
                    return resp
    return render_template_string(REGISTER_PAGE, error=error)

@web_bp.route("/logout")
def logout():
    me = current_user()
    token = request.cookies.get("session")
    if authmod:
        try:
            authmod.destroy_session(token)
        except Exception:
            pass
    if me:
        audit("logout", me["username"], uid=me["uid"], ip=_client_ip())
    resp = make_response(redirect(url_for("web.login")))
    resp.set_cookie("session", "", max_age=0, secure=SECURE_COOKIES)
    return resp

# ============================================================
# ROUTES: DASHBOARD
# ============================================================

@web_bp.route("/")
def index():
    me = current_user()
    if not me:
        return redirect(url_for("web.login"))
    try:
        logs = fetchall("SELECT time, event, data FROM logs ORDER BY id DESC LIMIT 20")
        logs = [{"time": fmt_time(r["time"]), "event": r["event"],
                 "data": r["data"]} for r in logs]
    except Exception:
        logs = []
    body = render_template_string(
        DASHBOARD_BODY, me=me, s=compute_stats(), logs=logs,
        default_days=DEFAULT_DAYS, default_max_devices=DEFAULT_MAX_DEVICES,
    )
    return page("Dashboard", me, body, "dashboard")

# ============================================================
# ROUTES: KEYS (với phân trang + lọc)
# ============================================================

@web_bp.route("/keys")
@require_login()
def keys():
    me = g.me
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "all")
    page_num = max(1, int(request.args.get("page", "1") or 1))
    offset = (page_num - 1) * PER_PAGE
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
    items, total, total_pages = [], 0, 1
    page_range = [1]
    try:
        total_row = fetchone(f"SELECT COUNT(*) AS c FROM keys {where_sql}",
                             tuple(params))
        total = total_row["c"] if total_row else 0
        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        rows = fetchall(
            f"SELECT * FROM keys {where_sql} "
            f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
            tuple(params) + (PER_PAGE, offset))
        now = now_ms()
        # Tránh N+1: lấy trước số device cho tất cả key trong 1 query
        device_counts = {}
        if rows:
            keys_list = [r["key"] for r in rows]
            placeholders = ",".join("?" * len(keys_list))
            try:
                dcr = fetchall(
                    f"SELECT key, COUNT(*) AS c FROM devices "
                    f"WHERE key IN ({placeholders}) GROUP BY key",
                    tuple(keys_list))
                device_counts = {r["key"]: r["c"] for r in dcr}
            except Exception:
                pass
        for r in rows:
            days_left = max(0, int((r["expires_at"] - now) / 86400000))
            items.append({
                "key": r["key"], "owner": r["owner"],
                "active": bool(r["active"]),
                "devicesUsed": device_counts.get(r["key"], 0),
                "maxDevices": r["max_devices"],
                "daysLeft": days_left,
                "expiresAtText": fmt_time(r["expires_at"]),
            })
        if total_pages > 1:
            start = max(1, page_num - 2)
            end = min(total_pages, page_num + 2)
            page_range = list(range(start, end + 1))
            if 1 not in page_range: page_range.insert(0, 1)
            if total_pages not in page_range: page_range.append(total_pages)
    except Exception as e:
        print(f"[WEB] keys lỗi: {e}")
    body = render_template_string(
        KEYS_BODY, me=me, keys=items, q=q, status=status,
        page=page_num, total_pages=total_pages, total=total,
        page_range=page_range)
    return page("Keys", me, body, "keys")

# ============================================================
# ROUTES: TREE / DEVICES / BLOCKS / CTV / ACCOUNTS / LOGS / API
# ============================================================

@web_bp.route("/tree")
@require_login()
def tree():
    me = g.me
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
@require_login()
def devices():
    me = g.me
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
@require_login()
def blocks():
    me = g.me
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
@require_login()
def ctv_page():
    me = g.me
    if me["role"] not in ("admin", "ctv"):
        abort(403)
    items = []
    try:
        rows = fetchall("SELECT * FROM ctv ORDER BY added_at DESC")
        items = [dict(r) for r in rows]
    except Exception:
        pass
    body = render_template_string(
        CTV_BODY, me=me, ctv=items,
        ctv_max_keys=CTV_MAX_KEYS, ctv_max_days=CTV_MAX_DAYS)
    return page("CTV", me, body, "ctv")

@web_bp.route("/accounts")
@require_login("admin")
def accounts_page():
    me = g.me
    items = []
    try:
        rows = fetchall("SELECT * FROM accounts ORDER BY created_at DESC")
        items = [dict(r) for r in rows]
    except Exception:
        pass
    body = render_template_string(
        ACCOUNTS_BODY, me=me, accounts=items,
        error=request.args.get("error", ""))
    return page("Tài khoản", me, body, "accounts")

@web_bp.route("/logs")
@require_login()
def logs_page():
    me = g.me
    try:
        n = int(request.args.get("n", 100))
    except ValueError:
        n = 100
    n = max(10, min(n, 1000))
    items = []
    try:
        rows = fetchall("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (n,))
        items = [{"time": fmt_time(r["time"]), "event": r["event"],
                  "data": r["data"]} for r in rows]
    except Exception:
        pass
    body = render_template_string(LOGS_BODY, me=me, logs=items, n=n)
    return page("Log", me, body, "logs")

@web_bp.route("/api")
@require_login("admin")
def api_manager():
    me = g.me
    items = []
    if apikey:
        try:
            items = apikey.list_api_keys()
        except Exception:
            pass
    body = render_template_string(API_MANAGER_BODY, me=me, api_keys=items)
    return page("API", me, body, "api")

# ============================================================
# ROUTES: MY PANEL
# ============================================================

@web_bp.route("/my")
@require_login()
def my_panel():
    me = g.me
    kr = None
    try:
        rec = fetchone("SELECT * FROM accounts WHERE uid = ?", (me["uid"],))
        key = rec["key"] if rec else None
        if key and keymod:
            kr = keymod.get_key_info(key)
    except Exception:
        pass
    success = request.args.get("success", "")
    error = request.args.get("error", "")
    toast = _toast(success, "ok") if success else (
        _toast(error, "err") if error else "")
    body = render_template_string(
        MY_PANEL_BODY, me=me, kr=kr, toast=toast)
    return page("Cá nhân", me, body, "my")

# ============================================================
# ACTIONS: CREATE / ISSUE / ADDDAYS / REVOKE / DELETE
# ============================================================

@web_bp.route("/web/create", methods=["POST"])
@require_login("write")
def web_create():
    me = g.me
    if not verify_csrf():
        return redirect(request.referrer or url_for("web.index"))
    if not keymod:
        return redirect(request.referrer or url_for("web.index"))
    try:
        days = int(request.form.get("days", 30))
        owner = request.form.get("owner", "").strip() or me["username"]
        max_dev = int(request.form.get("max_devices", 1))
        if days < 1 or days > 3650: days = 30
        if max_dev < 1 or max_dev > 1000: max_dev = 1
        keymod.create_key(days, owner, max_dev, created_by=me["username"])
        audit("create_key", f"{owner}|{days}d|{max_dev}dev",
              uid=me["uid"], ip=_client_ip())
    except Exception as e:
        print(f"[WEB] create lỗi: {e}")
    return redirect(request.referrer or url_for("web.index"))

@web_bp.route("/web/issue", methods=["POST"])
@require_login("issue")
def web_issue():
    me = g.me
    if not verify_csrf():
        return redirect(request.referrer or url_for("web.index"))
    if not keymod:
        return redirect(request.referrer or url_for("web.index"))
    user_id = request.form.get("user_id", "").strip()
    if not user_id:
        return redirect(request.referrer or url_for("web.index"))
    try:
        days = int(request.form.get("days", DEFAULT_DAYS))
        max_dev = int(request.form.get("max_devices", DEFAULT_MAX_DEVICES))
        keymod.create_key(days, f"user_{user_id}", max_dev, user_id=user_id)
        audit("issue_key", f"user={user_id}|{days}d",
              uid=me["uid"], ip=_client_ip())
    except Exception as e:
        print(f"[WEB] issue lỗi: {e}")
    return redirect(request.referrer or url_for("web.index"))

@web_bp.route("/web/adddays", methods=["POST"])
@require_login("write")
def web_adddays():
    me = g.me
    if not verify_csrf():
        return redirect(request.referrer or url_for("web.keys"))
    if keymod:
        try:
            k = request.form.get("key", "")
            d = int(request.form.get("days", 0))
            if d > 0 and d <= 3650:
                keymod.add_days(k, d)
                audit("add_days", f"{k[:16]}…|+{d}d",
                      uid=me["uid"], ip=_client_ip())
        except Exception:
            pass
    return redirect(request.referrer or url_for("web.keys"))

@web_bp.route("/web/revoke", methods=["POST"])
@require_login("write")
def web_revoke():
    me = g.me
    if not verify_csrf():
        return redirect(request.referrer or url_for("web.keys"))
    if keymod:
        try:
            k = request.form.get("key", "")
            if hasattr(keymod, "revoke_key"):
                keymod.revoke_key(k)
            else:
                execute("UPDATE keys SET active = 0 WHERE key = ?", (k,))
            audit("revoke_key", f"{k[:16]}…",
                  uid=me["uid"], ip=_client_ip())
        except Exception:
            pass
    return redirect(request.referrer or url_for("web.keys"))

@web_bp.route("/web/delete", methods=["POST"])
@require_login("delete")
def web_delete():
    me = g.me
    if not verify_csrf():
        return redirect(request.referrer or url_for("web.keys"))
    if keymod:
        try:
            k = request.form.get("key", "")
            if hasattr(keymod, "delete_key"):
                keymod.delete_key(k)
            else:
                execute("DELETE FROM keys WHERE key = ?", (k,))
            audit("delete_key", f"{k[:16]}…",
                  uid=me["uid"], ip=_client_ip())
        except Exception:
            pass
    return redirect(request.referrer or url_for("web.keys"))

# ============================================================
# ACTIONS: CTV
# ============================================================

@web_bp.route("/web/addctv", methods=["POST"])
@require_login("ctv")
def web_addctv():
    me = g.me
    if not verify_csrf():
        return redirect(url_for("web.ctv_page"))
    user_id = request.form.get("user_id", "").strip()
    if not user_id:
        return redirect(url_for("web.ctv_page"))
    try:
        from db import insert_or_ignore as ioi
        ioi("ctv", {
            "user_id": user_id,
            "name": request.form.get("name", "") or f"ctv_{user_id}",
            "max_keys": int(request.form.get("max_keys", CTV_MAX_KEYS)),
            "max_days": int(request.form.get("max_days", CTV_MAX_DAYS)),
            "keys_created": 0,
            "added_at": now_ms(),
            "active": 1,
        })
        audit("add_ctv", user_id, uid=me["uid"], ip=_client_ip())
    except Exception as e:
        print(f"[WEB] addctv lỗi: {e}")
    return redirect(url_for("web.ctv_page"))

@web_bp.route("/web/removectv", methods=["POST"])
@require_login("ctv")
def web_removectv():
    me = g.me
    if not verify_csrf():
        return redirect(url_for("web.ctv_page"))
    try:
        uid = request.form.get("user_id", "")
        execute("DELETE FROM ctv WHERE user_id = ?", (uid,))
        audit("remove_ctv", uid, uid=me["uid"], ip=_client_ip())
    except Exception:
        pass
    return redirect(url_for("web.ctv_page"))

@web_bp.route("/web/toggle_ctv", methods=["POST"])
@require_login("ctv")
def web_toggle_ctv():
    me = g.me
    if not verify_csrf():
        return redirect(url_for("web.ctv_page"))
    try:
        uid = request.form.get("user_id", "")
        execute("UPDATE ctv SET active = 1 - active WHERE user_id = ?", (uid,))
        audit("toggle_ctv", uid, uid=me["uid"], ip=_client_ip())
    except Exception:
        pass
    return redirect(url_for("web.ctv_page"))

# ============================================================
# ACTIONS: ACCOUNTS
# ============================================================

@web_bp.route("/accounts/create", methods=["POST"])
@require_login("admin")
def accounts_create():
    me = g.me
    if not verify_csrf() or not authmod:
        return redirect(url_for("web.accounts_page"))
    u = request.form.get("username", "").strip()
    p = request.form.get("password", "")
    try:
        ok, err = authmod.register_account(u, p)
        if ok:
            uid, _ = authmod.find_account_by_username(u)
            if uid:
                authmod.set_account_role(uid, request.form.get("role", "viewer"))
            audit("create_account", f"{u}|{request.form.get('role','viewer')}",
                  uid=me["uid"], ip=_client_ip())
            return redirect(url_for("web.accounts_page"))
    except Exception as e:
        err = str(e)
    return redirect(url_for("web.accounts_page", error=str(err)))

@web_bp.route("/accounts/remove", methods=["POST"])
@require_login("admin")
def accounts_remove():
    me = g.me
    if not verify_csrf() or not authmod:
        return redirect(url_for("web.accounts_page"))
    u = request.form.get("username", "")
    if u == me["username"]:
        return redirect(url_for("web.accounts_page",
                                error="Không thể xóa chính mình."))
    try:
        uid, _ = authmod.find_account_by_username(u)
        if uid:
            authmod.delete_account(uid)
            audit("delete_account", u, uid=me["uid"], ip=_client_ip())
    except Exception:
        pass
    return redirect(url_for("web.accounts_page"))

@web_bp.route("/accounts/toggle", methods=["POST"])
@require_login("admin")
def accounts_toggle():
    me = g.me
    if not verify_csrf() or not authmod:
        return redirect(url_for("web.accounts_page"))
    try:
        u = request.form.get("username", "")
        if u != me["username"]:
            uid, _ = authmod.find_account_by_username(u)
            if uid:
                authmod.toggle_account(uid)
                audit("toggle_account", u, uid=me["uid"], ip=_client_ip())
    except Exception:
        pass
    return redirect(url_for("web.accounts_page"))

# ============================================================
# ACTIONS: API MANAGER
# ============================================================

@web_bp.route("/api/create", methods=["POST"])
@require_login("admin")
def api_create():
    me = g.me
    if not verify_csrf() or not apikey:
        return redirect(url_for("web.api_manager"))
    try:
        raw = apikey.create_api_key(
            request.form.get("name", "client"),
            request.form.get("scopes", "verify,info").split(","),
            "client",
            int(request.form.get("rate_limit", 60)))
        audit("create_api_key", request.form.get("name", "client"),
              uid=me["uid"], ip=_client_ip())
        body = f"""
        <h1>✅ API KEY ĐÃ TẠO</h1>
        <div class="box">
          <div class="tree">{_esc(raw)}</div>
          <div class="alert warn mt">Lưu lại ngay. Không hiển thị lại.</div>
          <button class="neutral small mt"
                  onclick="navigator.clipboard.writeText('{_esc(raw)}')">📋 Copy</button>
        </div>
        <div class="box"><a href="/api">← Quay lại</a></div>"""
        return page("API Key", me, body, "api")
    except Exception:
        return redirect(url_for("web.api_manager"))

@web_bp.route("/api/toggle", methods=["POST"])
@require_login("admin")
def api_toggle():
    me = g.me
    if not verify_csrf() or not apikey:
        return redirect(url_for("web.api_manager"))
    try:
        apikey.toggle_api_key(request.form.get("key", ""))
        audit("toggle_api_key", request.form.get("key", "")[:16],
              uid=me["uid"], ip=_client_ip())
    except Exception:
        pass
    return redirect(url_for("web.api_manager"))

@web_bp.route("/api/delete", methods=["POST"])
@require_login("admin")
def api_delete():
    me = g.me
    if not verify_csrf() or not apikey:
        return redirect(url_for("web.api_manager"))
    try:
        apikey.delete_api_key(request.form.get("key", ""))
        audit("delete_api_key", request.form.get("key", "")[:16],
              uid=me["uid"], ip=_client_ip())
    except Exception:
        pass
    return redirect(url_for("web.api_manager"))

# ============================================================
# ACTIONS: MY PANEL
# ============================================================

@web_bp.route("/my/getkey", methods=["POST"])
@require_login()
def my_getkey():
    me = g.me
    if not verify_csrf() or not keymod:
        return redirect(url_for("web.my_panel", error="CSRF hoặc module lỗi"))
    try:
        rec = fetchone("SELECT key FROM accounts WHERE uid = ?", (me["uid"],))
        if rec and rec.get("key"):
            return redirect(url_for("web.my_panel", error="Bạn đã có key"))
        k, exp, sig = keymod.create_key(
            DEFAULT_DAYS, me["username"], DEFAULT_MAX_DEVICES,
            user_id=me["uid"])
        execute("UPDATE accounts SET key = ? WHERE uid = ?",
                (k, me["uid"]))
        audit("self_getkey", me["username"],
              uid=me["uid"], ip=_client_ip())
    except Exception as e:
        return redirect(url_for("web.my_panel", error=f"Lỗi: {e}"))
    return redirect(url_for("web.my_panel", success="Đã cấp key"))

@web_bp.route("/my/revoke", methods=["POST"])
@require_login()
def my_revoke():
    me = g.me
    if not verify_csrf() or not keymod:
        return redirect(url_for("web.my_panel"))
    try:
        rec = fetchone("SELECT key FROM accounts WHERE uid = ?", (me["uid"],))
        if rec and rec.get("key"):
            k = rec["key"]
            if hasattr(keymod, "revoke_key"):
                keymod.revoke_key(k)
            else:
                execute("UPDATE keys SET active = 0 WHERE key = ?", (k,))
            execute("UPDATE accounts SET key = NULL WHERE uid = ?", (me["uid"],))
            audit("self_revoke", me["username"],
                  uid=me["uid"], ip=_client_ip())
    except Exception:
        pass
    return redirect(url_for("web.my_panel", success="Đã thu hồi key"))

@web_bp.route("/my/changepw", methods=["POST"])
@require_login()
def my_changepw():
    me = g.me
    if not verify_csrf() or not authmod:
        return redirect(url_for("web.my_panel"))
    try:
        ok, err = authmod.change_account_password(
            me["uid"],
            request.form.get("old_password", ""),
            request.form.get("new_password", ""),
        )
    except Exception as e:
        ok, err = False, str(e)
    if not ok:
        return redirect(url_for("web.my_panel", error=str(err)))
    audit("change_password", me["username"],
          uid=me["uid"], ip=_client_ip())
    return redirect(url_for("web.my_panel", success="Đã đổi mật khẩu"))

# ============================================================
# ĐĂNG KÝ BLUEPRINT
# ============================================================

def register(app):
    """Đăng ký blueprint vào Flask app."""
    app.register_blueprint(web_bp)
    return web_bp
