import os
from dotenv import load_dotenv
load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

BROKER_HOST = "localhost"
BROKER_PORT = 1883
COLLECT_INTERVAL = 5
DB_PATH = "metrics.db"
DASHBOARD_HOST = "0.0.0.0"
DASHBOARD_PORT = 5000
DATA_RETENTION_DAYS = 7
CHART_POINTS = 120

TOPICS = {
    "cpu_usage": "system/cpu/usage",
    "cpu_temp":  "system/cpu/temp",
    "memory":    "system/memory",
    "disk":      "system/disk",
    "network":   "system/network",
}

ALERT_COOLDOWN = 600  # 10분

ALERT_THRESHOLDS = {
    "cpu_usage": 85.0,
    "cpu_temp":  80.0,
    "memory":    90.0,
    "disk":      90.0,
}

# 관리할 systemd 서비스 목록 — 본인 환경에 맞게 수정하세요
MANAGED_SERVICES = [
    "rustdesk",
    "waydroid-container",
    "smb",
    "tailscaled",
    "sshd",
    "mosquitto",
    "mqtt-publisher",
    "mqtt-subscriber",
    "mqtt-dashboard",
]

# 관리할 Docker 컨테이너 목록 — 없으면 빈 리스트로 두세요
MANAGED_CONTAINERS = [
    "upbit-bot",
    "upbit-dashboard",
]
