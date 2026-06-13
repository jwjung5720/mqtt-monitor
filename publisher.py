import json
import time
import logging
import psutil
import paho.mqtt.client as mqtt
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

_prev_net = None
_net_iface = None


def _get_active_iface() -> str | None:
    for name, s in psutil.net_if_stats().items():
        if name != "lo" and s.isup:
            return name
    return None


def _cpu_temp() -> float | None:
    try:
        temps = psutil.sensors_temperatures()
    except AttributeError:
        return None
    for key in ("coretemp", "k10temp", "acpitz"):
        entries = temps.get(key, [])
        if entries:
            return entries[0].current
    for entries in temps.values():
        if entries:
            return entries[0].current
    return None


def _network_bps() -> dict:
    global _prev_net, _net_iface

    if _net_iface is None:
        _net_iface = _get_active_iface()

    if _net_iface is None:
        return {"iface": None, "tx_bps": 0, "rx_bps": 0}

    counters = psutil.net_io_counters(pernic=True).get(_net_iface)
    if counters is None:
        return {"iface": _net_iface, "tx_bps": 0, "rx_bps": 0}

    now = time.time()
    if _prev_net is None:
        _prev_net = (now, counters.bytes_sent, counters.bytes_recv)
        return {"iface": _net_iface, "tx_bps": 0, "rx_bps": 0}

    prev_time, prev_tx, prev_rx = _prev_net
    elapsed = max(now - prev_time, 0.001)
    tx_bps = (counters.bytes_sent - prev_tx) / elapsed
    rx_bps = (counters.bytes_recv - prev_rx) / elapsed
    _prev_net = (now, counters.bytes_sent, counters.bytes_recv)

    return {"iface": _net_iface, "tx_bps": round(tx_bps), "rx_bps": round(rx_bps)}


def collect_and_publish(client: mqtt.Client) -> None:
    topics = config.TOPICS

    # interval=None으로 블로킹 없이 수집 (sleep은 메인 루프에서 담당)
    cpu_usage = psutil.cpu_percent(interval=None)
    client.publish(topics["cpu_usage"], str(cpu_usage), qos=1)

    temp = _cpu_temp()
    client.publish(topics["cpu_temp"], str(temp) if temp is not None else "null", qos=1)

    mem = psutil.virtual_memory().percent
    client.publish(topics["memory"], str(mem), qos=1)

    disk = psutil.disk_usage("/").percent
    client.publish(topics["disk"], str(disk), qos=1)

    net = _network_bps()
    client.publish(topics["network"], json.dumps(net), qos=1)

    log.info(f"CPU={cpu_usage}% TEMP={temp} MEM={mem}% DISK={disk}% NET={net}")


def main() -> None:
    client = mqtt.Client()
    client.connect(config.BROKER_HOST, config.BROKER_PORT, keepalive=60)
    client.loop_start()
    log.info(f"Connected to MQTT broker at {config.BROKER_HOST}:{config.BROKER_PORT}")

    try:
        while True:
            collect_and_publish(client)
            time.sleep(config.COLLECT_INTERVAL)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
