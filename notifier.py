import time
import logging
import requests
import config

log = logging.getLogger(__name__)

# {metric_key: last_alerted_timestamp}
_last_alerted: dict[str, float] = {}

_LABELS = {
    "cpu_usage": ("CPU 사용률",  "%",  "🔥"),
    "cpu_temp":  ("CPU 온도",    "°C", "🌡️"),
    "memory":    ("메모리 사용률", "%", "💾"),
    "disk":      ("디스크 사용률", "%", "💿"),
}


def _send(payload: dict) -> None:
    if not config.DISCORD_WEBHOOK_URL:
        log.warning("DISCORD_WEBHOOK_URL 미설정 — 알림 생략")
        return
    try:
        r = requests.post(config.DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        r.raise_for_status()
    except Exception as e:
        log.error(f"디스코드 알림 전송 실패: {e}")


def check_and_alert(metric_key: str, value: float) -> None:
    threshold = config.ALERT_THRESHOLDS.get(metric_key)
    if threshold is None or value is None:
        return
    if value < threshold:
        return

    now = time.time()
    if now - _last_alerted.get(metric_key, 0) < config.ALERT_COOLDOWN:
        return

    _last_alerted[metric_key] = now
    label, unit, emoji = _LABELS.get(metric_key, (metric_key, "", "⚠️"))

    _send({
        "embeds": [{
            "title": f"{emoji} 시스템 경보 — {label}",
            "description": (
                f"**{label}**이 임계값을 초과했습니다.\n\n"
                f"> 현재값: **{value:.1f}{unit}**\n"
                f"> 임계값: **{threshold:.1f}{unit}**"
            ),
            "color": 0xFF4444,
            "footer": {"text": "archlinux · mqtt-monitor"},
        }]
    })
    log.info(f"알림 전송: {label} {value:.1f}{unit} > {threshold}{unit}")
