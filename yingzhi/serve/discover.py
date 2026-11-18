"""发现本机 DeepWorks 内置 opencode server 的地址与凭证。

为什么需要「发现」而不是写死：
- 端口每次启动随机（当前是 60556，下次可能变）
- Basic Auth 用户名/密码由 DeepWorks 生成，存在引擎进程环境里
- 密码长度 64，属于私密信息，本模块只返回内存对象，不落盘、不打印

探测顺序：
1. 环境变量（OPENCODE_SERVER_URL / OPENCODE_SERVER_USERNAME / OPENCODE_SERVER_PASSWORD）
2. opencode-router 的 /health（它会返回 upstream opencode.url）
3. lsof 扫描 opencode 进程监听端口 + ps eww 读其环境

在 Linux 上 ps eww 同样可用；若被限制，可改用 /proc/<pid>/environ。
"""

import base64
import json
import os
import re
import shutil
import subprocess
import urllib.request

ROUTER_PORTS = ()  # 保留兼容；实际端口每次启动变化，靠进程反查
CACHE_TTL = 60
_cache = {"at": 0.0, "value": None}


class DiscoverError(RuntimeError):
    pass


def _http_json(url, headers=None, timeout=3):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _env_of(pid):
    """读取进程环境变量。macOS/Linux 均可，失败返回空字典。"""
    try:
        out = subprocess.run(
            ["ps", "eww", "-p", str(pid)],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return {}
    env = {}
    for token in out.split():
        if "=" in token:
            key, val = token.split("=", 1)
            env[key] = val
    return env


def _pids_matching(pattern):
    try:
        out = subprocess.run(
            ["pgrep", "-f", pattern], capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return []
    return [int(x) for x in re.findall(r"\d+", out)]


def _command_of(pid):
    try:
        return subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        return ""


def _router_pids():
    return _pids_matching("opencode-router")


def _server_pids():
    """opencode server 进程（排除 router）。重启后进程名/端口都会变，只能按命令行判断。"""
    result = []
    for pid in _pids_matching("sidecars/opencode"):
        if "router" in _command_of(pid):
            continue
        result.append(pid)
    return result


def _pid_on_port(port):
    lsof = shutil.which("lsof")
    if not lsof:
        return None
    try:
        out = subprocess.run(
            [lsof, "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN", "-t"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return None
    pids = [int(x) for x in re.findall(r"\d+", out)]
    return pids[0] if pids else None


def _listening_ports(pid):
    lsof = shutil.which("lsof")
    if not lsof:
        return []
    try:
        out = subprocess.run(
            [lsof, "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", str(pid)],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return []
    return sorted({int(m) for m in re.findall(r"127\.0\.0\.1:(\d+)", out)})


def _candidate_from_env():
    url = os.environ.get("OPENCODE_SERVER_URL")
    user = os.environ.get("OPENCODE_SERVER_USERNAME")
    pwd = os.environ.get("OPENCODE_SERVER_PASSWORD")
    if url and pwd:
        return _pack(url, user or "opencode", pwd, pid=None)
    return None


def _candidate_from_router():
    """router 的 /health 会返回 upstream opencode.url；端口由进程实时反查。"""
    for pid in _router_pids():
        for port in _listening_ports(pid):
            try:
                health = _http_json("http://127.0.0.1:%d/health" % port, timeout=2)
            except Exception:
                continue
            url = (health.get("opencode") or {}).get("url")
            if not url:
                continue
            try:
                srv_port = int(url.rsplit(":", 1)[-1].split("/")[0])
            except ValueError:
                continue
            srv_pid = _pid_on_port(srv_port)
            candidates = [srv_pid] if srv_pid else []
            candidates += [p for p in _server_pids() if p not in candidates]
            for spid in candidates:
                env = _env_of(spid)
                pwd = env.get("OPENCODE_SERVER_PASSWORD")
                if pwd:
                    return _pack(url, env.get("OPENCODE_SERVER_USERNAME") or "opencode", pwd, spid)
    return None


def _candidate_from_process():
    for pid in _server_pids():
        env = _env_of(pid)
        pwd = env.get("OPENCODE_SERVER_PASSWORD")
        if not pwd:
            continue
        ports = _listening_ports(pid)
        for port in ports:
            cand = _pack("http://127.0.0.1:%d" % port, env.get("OPENCODE_SERVER_USERNAME") or "opencode", pwd, pid)
            if _probe(cand):
                return cand
    return None


def _pack(url, user, password, pid):
    token = base64.b64encode(("%s:%s" % (user, password)).encode()).decode()
    return {
        "url": url.rstrip("/"),
        "username": user,
        "auth_header": "Basic " + token,
        "pid": pid,
    }


def _probe(cand):
    try:
        _http_json(cand["url"] + "/config", {"Authorization": cand["auth_header"]}, timeout=3)
        return True
    except Exception:
        return False


def discover(force=False):
    """返回 {url, username, auth_header, pid}；失败抛 DiscoverError。"""
    import time
    now = time.time()
    if not force and _cache["value"] and now - _cache["at"] < CACHE_TTL:
        return _cache["value"]

    for finder in (_candidate_from_env, _candidate_from_router, _candidate_from_process):
        try:
            cand = finder()
        except Exception:
            cand = None
        if cand and _probe(cand):
            _cache["at"] = now
            _cache["value"] = cand
            return cand

    raise DiscoverError(
        "找不到可用的 DeepWorks opencode server。请确认 DeepWorks 桌面端正在运行；"
        "若端口/凭证被系统限制，可显式设置 OPENCODE_SERVER_URL、"
        "OPENCODE_SERVER_USERNAME、OPENCODE_SERVER_PASSWORD。"
    )


if __name__ == "__main__":
    info = discover(force=True)
    print(json.dumps({k: v for k, v in info.items() if k != "auth_header"}, ensure_ascii=False))
    print("auth: Basic ***（已隐藏）")
