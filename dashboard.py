import json
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, jsonify, request, render_template
import config

app = Flask(__name__)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _row_to_entry(row: sqlite3.Row) -> dict:
    entry = {"timestamp": row["timestamp"]}
    if row["payload"]:
        entry.update(json.loads(row["payload"]))
    else:
        entry["value"] = row["value"]
    return entry


# ── 모니터링 API ───────────────────────────────────────────────────────────

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/metrics")
def api_metrics():
    topic = request.args.get("topic", "")
    try:
        limit = min(int(request.args.get("limit", config.CHART_POINTS)), 500)
    except ValueError:
        limit = config.CHART_POINTS
    conn = get_db()
    rows = conn.execute(
        "SELECT timestamp, value, payload FROM metrics WHERE topic=? ORDER BY timestamp DESC LIMIT ?",
        (topic, limit),
    ).fetchall()
    conn.close()
    return jsonify([_row_to_entry(r) for r in reversed(rows)])


@app.get("/api/latest")
def api_latest():
    conn = get_db()
    # 토픽별 최신값을 단일 쿼리로 조회
    placeholders = ",".join("?" * len(config.TOPICS))
    rows = conn.execute(
        f"""
        SELECT topic, timestamp, value, payload
        FROM metrics
        WHERE (topic, timestamp) IN (
            SELECT topic, MAX(timestamp) FROM metrics
            WHERE topic IN ({placeholders})
            GROUP BY topic
        )
        """,
        list(config.TOPICS.values()),
    ).fetchall()
    conn.close()

    by_topic = {r["topic"]: _row_to_entry(r) for r in rows}
    return jsonify({
        key: by_topic.get(topic)
        for key, topic in config.TOPICS.items()
    })


# ── 서비스 관리 API ────────────────────────────────────────────────────────

def _service_status(name: str) -> str:
    try:
        r = subprocess.run(
            ["sudo", "systemctl", "is-active", name],
            capture_output=True, text=True, timeout=3,
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"


def _container_status(name: str) -> str:
    try:
        r = subprocess.run(
            ["sudo", "docker", "inspect", "--format", "{{.State.Status}}", name],
            capture_output=True, text=True, timeout=3,
        )
        return r.stdout.strip() or "not found"
    except Exception:
        return "unknown"


@app.get("/api/services")
def api_services():
    tasks = (
        [(c, "docker") for c in config.MANAGED_CONTAINERS] +
        [(s, "systemd") for s in config.MANAGED_SERVICES]
    )

    results = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            ex.submit(
                _container_status if t == "docker" else _service_status, name
            ): (name, t)
            for name, t in tasks
        }
        for future in as_completed(futures):
            name, t = futures[future]
            results[(name, t)] = future.result()

    return jsonify([
        {"name": name, "status": results[(name, t)], "type": t}
        for name, t in tasks
    ])


def _run_service_action(name: str, action: str) -> tuple[bool, str]:
    if name in config.MANAGED_CONTAINERS:
        cmd = ["sudo", "docker", action, name]
        timeout = 15
    else:
        cmd = ["sudo", "systemctl", action, name]
        timeout = 10
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode == 0, r.stderr.strip()


@app.post("/api/services/<name>/start")
def svc_start(name):
    if name not in config.MANAGED_SERVICES and name not in config.MANAGED_CONTAINERS:
        return jsonify({"ok": False, "error": "unauthorized"}), 403
    ok, output = _run_service_action(name, "start")
    return jsonify({"ok": ok, "output": output})


@app.post("/api/services/<name>/stop")
def svc_stop(name):
    if name not in config.MANAGED_SERVICES and name not in config.MANAGED_CONTAINERS:
        return jsonify({"ok": False, "error": "unauthorized"}), 403
    ok, output = _run_service_action(name, "stop")
    return jsonify({"ok": ok, "output": output})


@app.post("/api/services/<name>/restart")
def svc_restart(name):
    if name not in config.MANAGED_SERVICES and name not in config.MANAGED_CONTAINERS:
        return jsonify({"ok": False, "error": "unauthorized"}), 403
    ok, output = _run_service_action(name, "restart")
    return jsonify({"ok": ok, "output": output})


# ── Tailscale API ──────────────────────────────────────────────────────────

@app.get("/api/tailscale")
def api_tailscale():
    try:
        r = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=5)
        data = json.loads(r.stdout)
        me = data.get("Self", {})
        peers = [{
            "hostname": me.get("HostName", ""),
            "ip": me.get("TailscaleIPs", [""])[0],
            "os": me.get("OS", ""),
            "online": True,
            "self": True,
        }]
        for peer in data.get("Peer", {}).values():
            peers.append({
                "hostname": peer.get("HostName", ""),
                "ip": (peer.get("TailscaleIPs") or [""])[0],
                "os": peer.get("OS", ""),
                "online": peer.get("Online", False),
                "last_seen": peer.get("LastSeen", ""),
                "self": False,
            })
        return jsonify(peers)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── 시스템 제어 API ────────────────────────────────────────────────────────

@app.post("/api/system/reboot")
def sys_reboot():
    subprocess.Popen(["sudo", "systemctl", "reboot"])
    return jsonify({"ok": True})


@app.post("/api/system/shutdown")
def sys_shutdown():
    subprocess.Popen(["sudo", "systemctl", "poweroff"])
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host=config.DASHBOARD_HOST, port=config.DASHBOARD_PORT, debug=False)
