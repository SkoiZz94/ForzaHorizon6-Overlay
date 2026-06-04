import pytest
from controller import ControllerState, _trigger_pct, SHIFT_UP_BTN, SHIFT_DOWN_BTN


class TestTriggerPct:
    def test_zero_gives_zero(self):
        assert _trigger_pct(0) == 0

    def test_max_gives_hundred(self):
        assert _trigger_pct(255) == 100

    def test_half(self):
        assert _trigger_pct(128) == pytest.approx(50, abs=1)

    def test_low_raw_rounds_to_zero(self):
        assert _trigger_pct(1) == 0    # 1/255*100 = 0.39 → 0

    def test_second_raw_rounds_to_one(self):
        assert _trigger_pct(2) == 1    # 2/255*100 = 0.78 → 1


class TestControllerState:
    def test_initially_not_connected(self):
        state = ControllerState()
        assert state.connected is False

    def test_initially_zero_triggers(self):
        state = ControllerState()
        assert state.lt_pct == 0
        assert state.rt_pct == 0

    def test_initially_shift_buttons_false(self):
        state = ControllerState()
        assert state.shift_up is False
        assert state.shift_down is False

    def test_button_constants_are_distinct(self):
        assert SHIFT_UP_BTN != SHIFT_DOWN_BTN

    def test_button_constants_are_valid_bitmasks(self):
        # XInput button bitmasks must be non-zero powers of two
        assert SHIFT_UP_BTN > 0 and (SHIFT_UP_BTN & (SHIFT_UP_BTN - 1)) == 0
        assert SHIFT_DOWN_BTN > 0 and (SHIFT_DOWN_BTN & (SHIFT_DOWN_BTN - 1)) == 0
