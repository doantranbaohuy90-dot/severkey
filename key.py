# key.py
# Module quản lý key: tạo, xác thực, cây key, thiết bị, block, dylib, thống kê
# Cải tiến: cache, tree nâng cao, batch, stats, revoke chain, export

import os
import json
import hmac
import hashlib
import secrets
import time
import threading
from datetime import datetime, timezone, timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
KEY_FILE = os.path.join(DATA_DIR, "keys.json")
DEVICE_FILE = os.path.join(DATA_DIR, "devices.json")
BLOCK_FILE = os.path.join(DATA_DIR, "blocked.json")
LOG_FILE = os.path.join(DATA_DIR, "logs.json")
TREE_FILE = os.path.join(DATA_DIR, "keytree.json")
STATS_FILE = os.path.join(DATA_DIR, "key_stats.json")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

lock = threading.RLock()

SECRET = os.environ.get("KEY_SECRET", "doi_thanh_bien_moi_truong")
DEFAULT_MAX_DEVICES = int(os.environ.get("DEFAULT_MAX_DEVICES", "1"))
DEFAULT_DAYS = int(os.environ.get("DEFAULT_DAYS", "1"))

# Tu dong gia han neu duoi nguong (0 = tat)
AUTO_RENEW_DAYS = int(os.environ.get("AUTO_RENEW_DAYS", "0"))

# So log toi da
LOG_MAX = int(os.environ.get("LOG_MAX", "5000"))

ALLOWED_DYLIB_HASHES = set(
    h.strip().lower() for h in os.environ.get("ALLOWED_DYLIB_HASHES", "").split(",") if h.strip()
)
BLOCKED_DYLIB_SIGNATURES = set(
    s.strip().lower() for s in os.environ.get("BLOCKED_DYLIB_SIGNATURES", "").split(",") if s.strip()
)


# ---------------- IO ----------------


def read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    with lock:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def now_ms():
    return int(time.time() * 1000)


def now_sec():
    return int(time.time())


def fmt_time(ms):
    if not ms:
        return "-"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def fmt_duration(ms):
    # Dinh dang khoang thoi gian thanh chuoi de doc
    if ms <= 0:
        return "0s"
    s = ms // 1000
    d = s // 86400
    h = (s % 86400) // 3600
    m = (s % 3600) // 60
    sec = s % 60
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if sec and not d: parts.append(f"{sec}s")
    return " ".join(parts) or "0s"


def load_keys():
    return read_json(KEY_FILE, {})


def save_keys(k):
    write_json(KEY_FILE, k)


def load_devices():
    return read_json(DEVICE_FILE, {})


def save_devices(d):
    write_json(DEVICE_FILE, d)


def load_blocked():
    return read_json(BLOCK_FILE, {"keys": {}, "devices": {}})


def save_blocked(b):
    write_json(BLOCK_FILE, b)


def load_tree():
    return read_json(TREE_FILE, {"roots": {}, "nodes": {}})


def save_tree(t):
    write_json(TREE_FILE, t)


def load_stats():
    return read_json(STATS_FILE, {
        "totalCreated": 0,
        "totalRevoked": 0,
        "totalDeleted": 0,
        "totalVerified": 0,
        "totalVerifyFail": 0,
        "totalDeviceBlocked": 0,
        "totalKeyBlocked": 0,
        "daily": {},
    })


def save_stats(s):
    write_json(STATS_FILE, s)


def _stats_bump(field, n=1):
    s = load_stats()
    s[field] = s.get(field, 0) + n
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day = s.setdefault("daily", {}).setdefault(today, {})
    day[field] = day.get(field, 0) + n
    save_stats(s)


def append_log(event, data):
    logs = read_json(LOG_FILE, [])
    logs.append({
        "time": datetime.now(timezone.utc).isoformat(),
        "ts": now_ms(),
        "event": event,
        "data": data,
    })
    if len(logs) > LOG_MAX:
        logs = logs[-LOG_MAX:]
    write_json(LOG_FILE, logs)


# ---------------- TIEN ICH ----------------


def generate_key(prefix="", groups=3, group_size=4):
    # Sinh key dang XXXX-XXXX-XXXX
    raw = secrets.token_hex(groups * group_size // 2).upper()
    body = "-".join(raw[i:i + group_size] for i in range(0, len(raw), group_size))
    return f"{prefix}{body}" if prefix else body


def sign_key(key, expires_at):
    payload = f"{key}|{expires_at}".encode("utf-8")
    return hmac.new(SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_signature(key, expires_at, signature):
    expected = sign_key(key, expires_at)
    return hmac.compare_digest(expected, signature)


def get_days_left(key):
    r = load_keys().get(key)
    if not r:
        return None
    ms = r["expiresAt"] - now_ms()
    return max(0, ms // (24 * 60 * 60 * 1000))


def get_ms_left(key):
    r = load_keys().get(key)
    if not r:
        return None
    return max(0, r["expiresAt"] - now_ms())


# ---------------- DYLIB ----------------


def check_dylib_list(dylibs):
    blocked, unknown, allowed = [], [], []
    for d in dylibs:
        name = str(d.get("name", "")).lower()
        h = str(d.get("hash", "")).lower()
        is_blocked = any(sig and (sig in name or sig in h) for sig in BLOCKED_DYLIB_SIGNATURES)
        if is_blocked:
            blocked.append({"name": name, "hash": h, "reason": "signature_blocked"})
            continue
        if ALLOWED_DYLIB_HASHES:
            if h in ALLOWED_DYLIB_HASHES:
                allowed.append({"name": name, "hash": h})
            else:
                unknown.append({"name": name, "hash": h})
        else:
            allowed.append({"name": name, "hash": h})
    injected = len(blocked) > 0
    return {
        "ok": not injected and len(unknown) == 0,
        "blocked": blocked, "unknown": unknown, "allowed": allowed,
        "injected": injected,
    }


# ---------------- BLOCK ----------------


def block_device(key, device_id, reason):
    b = load_blocked()
    b.setdefault("devices", {})[device_id] = {
        "key": key, "reason": reason, "time": now_ms()
    }
    save_blocked(b)
    _stats_bump("totalDeviceBlocked")
    append_log("device_block", {"key": key, "device": device_id, "reason": reason})


def unblock_device(device_id):
    b = load_blocked()
    if device_id in b.get("devices", {}):
        del b["devices"][device_id]
        save_blocked(b)
        append_log("device_unblock", {"device": device_id})
        return True
    return False


def block_key(key, reason):
    b = load_blocked()
    b.setdefault("keys", {})[key] = {"reason": reason, "time": now_ms()}
    save_blocked(b)
    _stats_bump("totalKeyBlocked")
    append_log("key_block", {"key": key, "reason": reason})


def unblock_key(key):
    b = load_blocked()
    if key in b.get("keys", {}):
        del b["keys"][key]
        save_blocked(b)
        append_log("key_unblock", {"key": key})
        return True
    return False


def is_device_blocked(device_id):
    return device_id in load_blocked().get("devices", {})


def is_key_blocked(key):
    return key in load_blocked().get("keys", {})


def list_blocked_devices():
    b = load_blocked()
    result = []
    for d, v in b.get("devices", {}).items():
        result.append({
            "device_id": d,
            "key": v.get("key"),
            "reason": v.get("reason"),
            "time": v.get("time"),
            "timeText": fmt_time(v.get("time", 0)),
        })
    return result


def list_blocked_keys():
    b = load_blocked()
    result = []
    for k, v in b.get("keys", {}).items():
        result.append({
            "key": k,
            "reason": v.get("reason"),
            "time": v.get("time"),
            "timeText": fmt_time(v.get("time", 0)),
        })
    return result


# ---------------- CAY KEY ----------------


def add_tree_node(key, parent_key=None, owner=None, meta=None):
    # Thêm key vào cây, parent_key=None nghĩa là gốc
    tree = load_tree()
    node = {
        "key": key,
        "parent": parent_key,
        "owner": owner,
        "createdAt": now_ms(),
        "children": [],
        "meta": meta or {},
    }
    tree.setdefault("nodes", {})[key] = node
    if parent_key and parent_key in tree["nodes"]:
        tree["nodes"][parent_key].setdefault("children", []).append(key)
    else:
        tree.setdefault("roots", {})[key] = True
    save_tree(tree)
    return node


def remove_tree_node(key):
    # Xóa nút và gán con lên cha
    tree = load_tree()
    nodes = tree.get("nodes", {})
    if key not in nodes:
        return False
    node = nodes[key]
    parent = node.get("parent")
    for child in node.get("children", []):
        if child in nodes:
            nodes[child]["parent"] = parent
            if parent and parent in nodes:
                nodes[parent].setdefault("children", []).append(child)
            else:
                tree.setdefault("roots", {})[child] = True
    if parent and parent in nodes:
        nodes[parent]["children"] = [c for c in nodes[parent].get("children", []) if c != key]
    tree.get("roots", {}).pop(key, None)
    del nodes[key]
    save_tree(tree)
    return True


def get_tree():
    return load_tree()


def build_tree_view():
    # Trả về cây dạng nested dict để render
    tree = load_tree()
    nodes = tree.get("nodes", {})
    roots = tree.get("roots", {})

    def build(k, depth=0, seen=None):
        if seen is None:
            seen = set()
        if k in seen:
            return None  # chan vong lap
        seen.add(k)
        node = nodes.get(k, {})
        return {
            "key": k,
            "owner": node.get("owner"),
            "createdAt": node.get("createdAt"),
            "createdAtText": fmt_time(node.get("createdAt", 0)),
            "daysLeft": get_days_left(k),
            "depth": depth,
            "meta": node.get("meta", {}),
            "children": [c for c in (
                build(c, depth + 1, set(seen)) for c in node.get("children", []) if c in nodes
            ) if c],
        }

    return [t for t in (build(k) for k in roots if k in nodes) if t]


def render_tree_text(node_list, prefix="", is_last=True):
    # Sinh text ASCII cho cây
    lines = []
    for i, node in enumerate(node_list):
        last = i == len(node_list) - 1
        branch = "└── " if last else "├── "
        key = node["key"]
        owner = node.get("owner") or "-"
        days = node.get("daysLeft")
        days_str = f"{days}d" if days is not None else "-"
        lines.append(f"{prefix}{branch}{key} [{owner}] {days_str}")
        child_prefix = prefix + ("    " if last else "│   ")
        if node.get("children"):
            lines.extend(render_tree_text(node["children"], child_prefix, last))
    return lines


def get_tree_children(key):
    tree = load_tree()
    node = tree.get("nodes", {}).get(key, {})
    return list(node.get("children", []))


def get_all_descendants(key):
    # Trả về toàn bộ key con cháu
    result = []
    stack = list(get_tree_children(key))
    seen = set()
    while stack:
        k = stack.pop()
        if k in seen:
            continue
        seen.add(k)
        result.append(k)
        stack.extend(get_tree_children(k))
    return result


def get_all_ancestors(key):
    # Trả về toàn bộ key cha ông
    tree = load_tree()
    nodes = tree.get("nodes", {})
    result = []
    cur = nodes.get(key, {}).get("parent")
    seen = set()
    while cur and cur not in seen:
        seen.add(cur)
        result.append(cur)
        cur = nodes.get(cur, {}).get("parent")
    return result


# ---------------- NGHIEP VU KEY ----------------


def create_key(days, owner, max_devices=DEFAULT_MAX_DEVICES, user_id=None,
               created_by=None, account_uid=None, parent_key=None, meta=None):
    key = generate_key()
    expires_at = now_ms() + days * 24 * 60 * 60 * 1000
    signature = sign_key(key, expires_at)
    keys = load_keys()
    keys[key] = {
        "owner": owner,
        "expiresAt": expires_at,
        "signature": signature,
        "active": True,
        "maxDevices": int(max_devices),
        "createdAt": now_ms(),
        "userId": user_id,
        "createdBy": str(created_by) if created_by else None,
        "accountUid": account_uid,
        "parent": parent_key,
        "meta": meta or {},
        "verifyCount": 0,
        "lastVerified": None,
    }
    save_keys(keys)

    add_tree_node(
        key, parent_key=parent_key, owner=owner,
        meta={"userId": user_id, "createdBy": str(created_by) if created_by else None,
              "accountUid": account_uid, "days": days},
    )

    _stats_bump("totalCreated")
    append_log("key_create", {
        "key": key, "owner": owner, "days": days, "maxDevices": max_devices,
        "userId": user_id, "createdBy": str(created_by) if created_by else None,
        "accountUid": account_uid, "parent": parent_key,
    })
    return key, expires_at, signature


def add_days(key, days):
    keys = load_keys()
    if key not in keys:
        return None
    base = max(keys[key]["expiresAt"], now_ms())
    new_exp = base + days * 24 * 60 * 60 * 1000
    keys[key]["expiresAt"] = new_exp
    keys[key]["signature"] = sign_key(key, new_exp)
    keys[key]["active"] = True
    save_keys(keys)
    append_log("key_adddays", {"key": key, "days": days, "newExpiresAt": new_exp})
    return new_exp


def set_expiry(key, days_from_now):
    keys = load_keys()
    if key not in keys:
        return None
    new_exp = now_ms() + days_from_now * 24 * 60 * 60 * 1000
    keys[key]["expiresAt"] = new_exp
    keys[key]["signature"] = sign_key(key, new_exp)
    keys[key]["active"] = True
    save_keys(keys)
    append_log("key_setexp", {"key": key, "daysFromNow": days_from_now, "newExpiresAt": new_exp})
    return new_exp


def revoke_key(key, cascade=False):
    # Thu hồi key, cascade=True thu hồi cả con cháu
    keys = load_keys()
    if key not in keys:
        return False
    keys[key]["active"] = False
    save_keys(keys)
    _stats_bump("totalRevoked")
    append_log("key_revoke", {"key": key, "cascade": cascade})
    if cascade:
        for child in get_all_descendants(key):
            if child in keys and keys[child].get("active"):
                keys[child]["active"] = False
        save_keys(keys)
    return True


def reset_devices(key):
    devices = load_devices()
    if key in devices:
        del devices[key]
        save_devices(devices)
    append_log("device_reset", {"key": key})
    return True


def delete_key(key, cascade=False):
    keys = load_keys()
    if key not in keys:
        return False
    user_id = keys[key].get("userId")
    account_uid = keys[key].get("accountUid")
    del keys[key]
    save_keys(keys)
    devices = load_devices()
    if key in devices:
        del devices[key]
        save_devices(devices)
    remove_tree_node(key)
    _stats_bump("totalDeleted")
    append_log("key_delete", {"key": key, "userId": user_id, "accountUid": account_uid,
                              "cascade": cascade})
    if cascade:
        for child in get_all_descendants(key):
            delete_key(child, cascade=False)
    return True


def batch_create(days, owner, count, max_devices=DEFAULT_MAX_DEVICES, prefix=None):
    # Tạo nhiều key cùng lúc, trả về danh sách key
    result = []
    for i in range(int(count)):
        k, exp, sig = create_key(days, owner, max_devices)
        result.append({"key": k, "expiresAt": exp, "signature": sig})
    return result


def verify_key(key, device_id, ip, user_agent, dylibs=None):
    if is_key_blocked(key):
        _stats_bump("totalVerifyFail")
        append_log("verify_fail", {"key": key, "reason": "key_blocked",
                                   "device": device_id, "ip": ip})
        return {"ok": False, "error": "key_blocked"}

    if is_device_blocked(device_id):
        _stats_bump("totalVerifyFail")
        append_log("verify_fail", {"key": key, "reason": "device_blocked",
                                   "device": device_id, "ip": ip})
        return {"ok": False, "error": "device_blocked"}

    keys = load_keys()
    record = keys.get(key)
    if not record:
        _stats_bump("totalVerifyFail")
        append_log("verify_fail", {"key": key, "reason": "not_found",
                                   "device": device_id, "ip": ip})
        return {"ok": False, "error": "key_not_found"}

    if not record.get("active"):
        _stats_bump("totalVerifyFail")
        append_log("verify_fail", {"key": key, "reason": "disabled",
                                   "device": device_id, "ip": ip})
        return {"ok": False, "error": "key_disabled"}

    if now_ms() > record["expiresAt"]:
        _stats_bump("totalVerifyFail")
        append_log("verify_fail", {"key": key, "reason": "expired",
                                   "device": device_id, "ip": ip})
        return {"ok": False, "error": "key_expired"}

    # Kiem tra chu ky neu co
    if record.get("signature") and not verify_signature(key, record["expiresAt"], record["signature"]):
        append_log("verify_fail", {"key": key, "reason": "signature_invalid",
                                   "device": device_id, "ip": ip})

    # Kiem tra dylib
    dylib_result = None
    if dylibs is not None:
        dylib_result = check_dylib_list(dylibs)
        if dylib_result["injected"]:
            block_device(key, device_id, "dylib_injected")
            append_log("dylib_injected", {"key": key, "device": device_id,
                                          "blocked": dylib_result["blocked"]})
            return {"ok": False, "error": "dylib_injected",
                    "detail": dylib_result, "device_blocked": True}
        if dylib_result["unknown"]:
            append_log("dylib_unknown", {"key": key, "device": device_id,
                                         "unknown": dylib_result["unknown"]})
            return {"ok": False, "error": "dylib_unknown", "detail": dylib_result}

    # Dang ky thiet bi
    devices = load_devices()
    key_devices = devices.get(key, {})
    max_dev = record.get("maxDevices", DEFAULT_MAX_DEVICES)

    if device_id not in key_devices:
        if len(key_devices) >= max_dev:
            _stats_bump("totalVerifyFail")
            append_log("verify_fail", {"key": key, "reason": "device_limit",
                                       "device": device_id, "ip": ip})
            return {"ok": False, "error": "device_limit_reached", "maxDevices": max_dev}
        key_devices[device_id] = {
            "firstSeen": now_ms(), "lastSeen": now_ms(), "ip": ip,
            "userAgent": user_agent, "count": 1,
            "dylibHash": [d.get("hash") for d in (dylibs or [])],
        }
    else:
        key_devices[device_id]["lastSeen"] = now_ms()
        key_devices[device_id]["ip"] = ip
        key_devices[device_id]["userAgent"] = user_agent
        key_devices[device_id]["count"] = key_devices[device_id].get("count", 0) + 1
        key_devices[device_id]["dylibHash"] = [d.get("hash") for d in (dylibs or [])]

    devices[key] = key_devices
    save_devices(devices)

    # Cap nhat verify count
    keys[key]["verifyCount"] = record.get("verifyCount", 0) + 1
    keys[key]["lastVerified"] = now_ms()
    save_keys(keys)

    _stats_bump("totalVerified")
    append_log("verify_ok", {"key": key, "device": device_id, "ip": ip})

    remaining_ms = record["expiresAt"] - now_ms()
    remaining_days = remaining_ms // (24 * 60 * 60 * 1000)

    return {
        "ok": True,
        "owner": record["owner"],
        "expiresAt": record["expiresAt"],
        "expiresAtText": fmt_time(record["expiresAt"]),
        "remainingDays": remaining_days,
        "remainingMs": remaining_ms,
        "remainingText": fmt_duration(remaining_ms),
        "signature": record["signature"],
        "devicesUsed": len(key_devices),
        "maxDevices": max_dev,
        "dylib": dylib_result,
    }


def get_key_info(key):
    kr = load_keys().get(key)
    if not kr:
        return None
    devices = load_devices().get(key, {})
    ms_left = max(0, kr["expiresAt"] - now_ms())
    return {
        "key": key,
        "owner": kr["owner"],
        "active": kr.get("active", False),
        "blocked": is_key_blocked(key),
        "expiresAt": kr["expiresAt"],
        "expiresAtText": fmt_time(kr["expiresAt"]),
        "daysLeft": get_days_left(key),
        "msLeft": ms_left,
        "remainingText": fmt_duration(ms_left),
        "maxDevices": kr.get("maxDevices", DEFAULT_MAX_DEVICES),
        "devicesUsed": len(devices),
        "signature": kr.get("signature"),
        "createdAt": kr.get("createdAt"),
        "createdAtText": fmt_time(kr.get("createdAt", 0)),
        "createdBy": kr.get("createdBy"),
        "userId": kr.get("userId"),
        "accountUid": kr.get("accountUid"),
        "parent": kr.get("parent"),
        "children": get_tree_children(key),
        "ancestors": get_all_ancestors(key),
        "verifyCount": kr.get("verifyCount", 0),
        "lastVerified": kr.get("lastVerified"),
        "lastVerifiedText": fmt_time(kr["lastVerified"]) if kr.get("lastVerified") else "-",
        "meta": kr.get("meta", {}),
    }


def list_keys(filter_active=None, filter_blocked=None, owner_like=None, sort_by="createdAt"):
    keys = load_keys()
    devices = load_devices()
    result = []
    for k, v in keys.items():
        blocked = is_key_blocked(k)
        if filter_active is not None and v.get("active", False) != filter_active:
            continue
        if filter_blocked is not None and blocked != filter_blocked:
            continue
        if owner_like and owner_like.lower() not in str(v.get("owner", "")).lower():
            continue
        ms_left = max(0, v["expiresAt"] - now_ms())
        result.append({
            "key": k,
            "owner": v["owner"],
            "active": v.get("active", False),
            "blocked": blocked,
            "expiresAt": v["expiresAt"],
            "expiresAtText": fmt_time(v["expiresAt"]),
            "daysLeft": get_days_left(k),
            "msLeft": ms_left,
            "maxDevices": v.get("maxDevices", DEFAULT_MAX_DEVICES),
            "devicesUsed": len(devices.get(k, {})),
            "userId": v.get("userId"),
            "createdBy": v.get("createdBy"),
            "accountUid": v.get("accountUid"),
            "parent": v.get("parent"),
            "createdAt": v.get("createdAt", 0),
            "createdAtText": fmt_time(v.get("createdAt", 0)),
            "verifyCount": v.get("verifyCount", 0),
        })
    # Sap xep
    if sort_by == "createdAt":
        result.sort(key=lambda x: x.get("createdAt", 0), reverse=True)
    elif sort_by == "expiresAt":
        result.sort(key=lambda x: x.get("expiresAt", 0))
    elif sort_by == "daysLeft":
        result.sort(key=lambda x: x.get("daysLeft", 0))
    elif sort_by == "owner":
        result.sort(key=lambda x: str(x.get("owner", "")).lower())
    return result


def list_devices_of(key):
    devices = load_devices().get(key, {})
    result = []
    for dev_id, info in devices.items():
        result.append({
            "device_id": dev_id,
            "ip": info.get("ip"),
            "firstSeen": info.get("firstSeen"),
            "firstSeenText": fmt_time(info.get("firstSeen", 0)),
            "lastSeen": info.get("lastSeen"),
            "lastSeenText": fmt_time(info.get("lastSeen", 0)),
            "count": info.get("count", 0),
            "blocked": is_device_blocked(dev_id),
        })
    return result


def list_all_devices():
    devices_map = load_devices()
    result = []
    for k, devs in devices_map.items():
        for dev_id, info in devs.items():
            result.append({
                "device_id": dev_id,
                "key": k,
                "ip": info.get("ip"),
                "firstSeenText": fmt_time(info.get("firstSeen", 0)),
                "lastSeenText": fmt_time(info.get("lastSeen", 0)),
                "count": info.get("count", 0),
                "blocked": is_device_blocked(dev_id),
            })
    result.sort(key=lambda x: x.get("lastSeenText", ""), reverse=True)
    return result


# ---------------- BAO CAO ----------------


def get_stats_summary():
    keys = load_keys()
    devices = load_devices()
    blocked = load_blocked()
    stats = load_stats()

    active = sum(1 for v in keys.values() if v.get("active"))
    expired = sum(1 for v in keys.values() if now_ms() > v.get("expiresAt", 0))
    total_devices = sum(len(v) for v in devices.values())

    # Sap het han trong 3 ngay
    soon = 0
    threshold = now_ms() + 3 * 24 * 60 * 60 * 1000
    for v in keys.values():
        exp = v.get("expiresAt", 0)
        if exp > now_ms() and exp <= threshold:
            soon += 1

    return {
        "totalKeys": len(keys),
        "activeKeys": active,
        "expiredKeys": expired,
        "disabledKeys": len(keys) - active,
        "soonExpiring": soon,
        "totalDevices": total_devices,
        "blockedKeys": len(blocked.get("keys", {})),
        "blockedDevices": len(blocked.get("devices", {})),
        "totalCreated": stats.get("totalCreated", 0),
        "totalRevoked": stats.get("totalRevoked", 0),
        "totalDeleted": stats.get("totalDeleted", 0),
        "totalVerified": stats.get("totalVerified", 0),
        "totalVerifyFail": stats.get("totalVerifyFail", 0),
        "totalDeviceBlocked": stats.get("totalDeviceBlocked", 0),
        "totalKeyBlocked": stats.get("totalKeyBlocked", 0),
    }


def get_daily_stats(days=7):
    # Trả về thống kê theo ngày trong n ngày gần nhất
    stats = load_stats()
    daily = stats.get("daily", {})
    result = []
    now = datetime.now(timezone.utc)
    for i in range(days - 1, -1, -1):
        d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        rec = daily.get(d, {})
        result.append({
            "date": d,
            "created": rec.get("totalCreated", 0),
            "verified": rec.get("totalVerified", 0),
            "failed": rec.get("totalVerifyFail", 0),
            "revoked": rec.get("totalRevoked", 0),
        })
    return result


def cleanup_expired(days_after=30):
    # Xoa key het han qua n ngay
    threshold = now_ms() - days_after * 24 * 60 * 60 * 1000
    keys = load_keys()
    to_delete = [k for k, v in keys.items() if v.get("expiresAt", 0) < threshold]
    for k in to_delete:
        delete_key(k)
    append_log("cleanup_expired", {"count": len(to_delete), "days": days_after})
    return len(to_delete)


def export_keys(format="json"):
    # Xuat danh sach key
    keys = list_keys()
    if format == "json":
        return json.dumps(keys, ensure_ascii=False, indent=2)
    if format == "csv":
        lines = ["key,owner,active,blocked,expiresAt,daysLeft,maxDevices,devicesUsed"]
        for k in keys:
            lines.append(f"{k['key']},{k['owner']},{k['active']},{k['blocked']},"
                         f"{k['expiresAtText']},{k['daysLeft']},{k['maxDevices']},{k['devicesUsed']}")
        return "\n".join(lines)
    return ""
