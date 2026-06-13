import sys
import os
import publisher

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_network_bps_first_call_returns_zero():
    publisher._prev_net = None
    publisher._net_iface = "eth0"

    from unittest.mock import patch, MagicMock
    counter = MagicMock(bytes_sent=1000, bytes_recv=2000)

    with patch("psutil.net_io_counters", return_value={"eth0": counter}):
        result = publisher._network_bps()

    assert result["tx_bps"] == 0
    assert result["rx_bps"] == 0
    assert result["iface"] == "eth0"


def test_network_bps_calculates_delta():
    import time
    publisher._net_iface = "eth0"

    from unittest.mock import patch, MagicMock
    counter = MagicMock(bytes_sent=2000, bytes_recv=4000)
    publisher._prev_net = (time.time() - 1.0, 1000, 2000)  # 1초 전, tx=1000, rx=2000

    with patch("psutil.net_io_counters", return_value={"eth0": counter}):
        result = publisher._network_bps()

    assert result["tx_bps"] == pytest.approx(1000, rel=0.1)
    assert result["rx_bps"] == pytest.approx(2000, rel=0.1)


def test_cpu_temp_fallback_order():
    from unittest.mock import patch

    with patch("psutil.sensors_temperatures", return_value={"acpitz": [type("T", (), {"current": 55.0})()]}):
        temp = publisher._cpu_temp()
        assert temp == 55.0


def test_cpu_temp_returns_none_when_no_sensors():
    from unittest.mock import patch

    with patch("psutil.sensors_temperatures", return_value={}):
        temp = publisher._cpu_temp()
        assert temp is None


import pytest
