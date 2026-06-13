import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta, timezone
import paho.mqtt.client as mqtt
import config
import notifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

_last_cleanup = 0
CLEANUP_INTERVAL = 3600

# 토픽 → 메트릭 키 역매핑 (메시지마다 재생성 방지)
_TOPIC_TO_KEY: dict[str, str] = {v: k for k, v in config.TOPICS.items()}


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            topic     TEXT NOT NULL,
            value     REAL,
            payload   TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_metrics_topic_ts ON metrics (topic, timestamp)
    """)
    # WAL 모드: 읽기/쓰기 동시성 향상
    conn.execute("PRAGMA journal_mode=WAL")
    conn.commit()


def cleanup_old(conn: sqlite3.Connection) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=config.DATA_RETENTION_DAYS)).isoformat()
    conn.execute("DELETE FROM metrics WHERE timestamp < ?", (cutoff,))
    conn.commit()


def on_message(conn: sqlite3.Connection, topic: str, payload_str: str) -> None:
    global _last_cleanup

    value = None
    payload = None

    try:
        parsed = json.loads(payload_str)
        if isinstance(parsed, dict):
            payload = payload_str
        else:
            value = float(parsed) if parsed != "null" else None
    except (json.JSONDecodeError, ValueError):
        try:
            value = float(payload_str) if payload_str != "null" else None
        except ValueError:
            payload = payload_str

    conn.execute(
        "INSERT INTO metrics (topic, value, payload) VALUES (?, ?, ?)",
        (topic, value, payload),
    )
    conn.commit()

    if value is not None:
        metric_key = _TOPIC_TO_KEY.get(topic)
        if metric_key:
            notifier.check_and_alert(metric_key, value)

    now = time.time()
    if now - _last_cleanup > CLEANUP_INTERVAL:
        cleanup_old(conn)
        _last_cleanup = now
        log.info("오래된 메트릭 정리 완료")


def main() -> None:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    init_db(conn)
    log.info(f"DB 초기화 완료: {config.DB_PATH}")

    all_topics = list(config.TOPICS.values())
    client = mqtt.Client()

    def _on_message(_client, _userdata, msg):
        try:
            on_message(conn, msg.topic, msg.payload.decode())
        except Exception as e:
            log.error(f"메시지 처리 오류: {e}")

    def _on_connect(_client, _userdata, _flags, rc):
        if rc == 0:
            for topic in all_topics:
                _client.subscribe(topic, qos=1)
            log.info(f"구독 시작: {all_topics}")
        else:
            log.error(f"MQTT 연결 실패: rc={rc}")

    client.on_connect = _on_connect
    client.on_message = _on_message
    client.connect(config.BROKER_HOST, config.BROKER_PORT, keepalive=60)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()
        client.disconnect()


if __name__ == "__main__":
    main()
