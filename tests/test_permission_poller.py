# tests/test_permission_poller.py
from codogram.permission_poller import PollerState

def test_poller_state_enum():
    assert PollerState.IDLE.value == "idle"
    assert PollerState.DEBOUNCING.value == "debouncing"
    assert PollerState.SHOWING.value == "showing"
