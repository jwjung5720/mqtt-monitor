import time
from unittest.mock import patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import notifier
import config


def setup_function():
    notifier._last_alerted.clear()


def test_no_alert_below_threshold():
    with patch("notifier._send") as mock_send:
        notifier.check_and_alert("cpu_usage", config.ALERT_THRESHOLDS["cpu_usage"] - 1)
        mock_send.assert_not_called()


def test_alert_at_threshold():
    with patch("notifier._send") as mock_send:
        notifier.check_and_alert("cpu_usage", config.ALERT_THRESHOLDS["cpu_usage"])
        mock_send.assert_called_once()


def test_alert_above_threshold():
    with patch("notifier._send") as mock_send:
        notifier.check_and_alert("cpu_usage", 99.0)
        mock_send.assert_called_once()


def test_cooldown_blocks_second_alert():
    with patch("notifier._send") as mock_send:
        notifier.check_and_alert("cpu_usage", 99.0)
        notifier.check_and_alert("cpu_usage", 99.0)
        assert mock_send.call_count == 1


def test_cooldown_allows_after_expiry():
    with patch("notifier._send") as mock_send:
        notifier.check_and_alert("memory", 95.0)
        # 쿨다운 만료 시뮬레이션
        notifier._last_alerted["memory"] -= config.ALERT_COOLDOWN + 1
        notifier.check_and_alert("memory", 95.0)
        assert mock_send.call_count == 2


def test_independent_cooldown_per_metric():
    with patch("notifier._send") as mock_send:
        notifier.check_and_alert("cpu_usage", 99.0)
        notifier.check_and_alert("memory", 95.0)
        assert mock_send.call_count == 2


def test_unknown_metric_ignored():
    with patch("notifier._send") as mock_send:
        notifier.check_and_alert("nonexistent_metric", 999.0)
        mock_send.assert_not_called()
