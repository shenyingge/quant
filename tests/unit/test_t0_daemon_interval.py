from types import SimpleNamespace
from unittest.mock import patch

import main


def test_get_t0_poll_interval_seconds_uses_configured_value():
    with patch.object(main, "settings", SimpleNamespace(t0_poll_interval_seconds=15)):
        assert main._get_t0_poll_interval_seconds() == 15


def test_get_t0_poll_interval_seconds_clamps_invalid_values():
    with patch.object(main, "settings", SimpleNamespace(t0_poll_interval_seconds=0)):
        assert main._get_t0_poll_interval_seconds() == 1
