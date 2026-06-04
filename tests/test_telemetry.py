import struct
import pytest
from telemetry import (
    parse_packet, compute_ratio, lights_state, TelemetryState,
    COLOR_GREEN, COLOR_YELLOW, COLOR_RED, COLOR_FLASH, COLOR_UNLIT,
    NUM_LIGHTS, SHIFT_RATIO,
)


def make_packet(current_rpm=5000.0, idle_rpm=800.0, max_rpm=9000.0, gear=0) -> bytes:
    data = bytearray(324)
    struct.pack_into("<f", data, 8,  max_rpm)
    struct.pack_into("<f", data, 12, idle_rpm)
    struct.pack_into("<f", data, 16, current_rpm)
    struct.pack_into("<B", data, 319, gear)
    return bytes(data)


class TestParsePacket:
    def test_extracts_all_four_values(self):
        data = make_packet(current_rpm=5000.0, idle_rpm=800.0, max_rpm=9000.0, gear=4)
        current, idle, max_rpm, gear = parse_packet(data)
        assert current  == pytest.approx(5000.0)
        assert idle     == pytest.approx(800.0)
        assert max_rpm  == pytest.approx(9000.0)
        assert gear     == 4

    def test_raises_on_short_packet(self):
        with pytest.raises(struct.error):
            parse_packet(b"\x00" * 10)

    def test_raises_on_empty_packet(self):
        with pytest.raises(struct.error):
            parse_packet(b"")

    def test_gear_parsed_correctly(self):
        data = make_packet(gear=3)
        _, _, _, gear = parse_packet(data)
        assert gear == 3

    def test_gear_zero_on_short_packet(self):
        short = make_packet()[:232]
        _, _, _, gear = parse_packet(short)
        assert gear == 0

    def test_neutral_gear(self):
        data = make_packet(gear=0)
        _, _, _, gear = parse_packet(data)
        assert gear == 0

    def test_reverse_gear(self):
        data = make_packet(gear=11)
        _, _, _, gear = parse_packet(data)
        assert gear == 11

    def test_reverse_gear_255_normalised(self):
        data = make_packet(gear=255)
        _, _, _, gear = parse_packet(data)
        assert gear == 11


class TestComputeRatio:
    def test_idle_rpm_gives_zero(self):
        assert compute_ratio(800.0, 800.0, 9000.0) == pytest.approx(0.0)

    def test_max_rpm_gives_one(self):
        assert compute_ratio(9000.0, 800.0, 9000.0) == pytest.approx(1.0)

    def test_midpoint(self):
        # (4900 - 800) / (9000 - 800) = 4100 / 8200 = 0.5
        assert compute_ratio(4900.0, 800.0, 9000.0) == pytest.approx(0.5)

    def test_clamps_above_max(self):
        assert compute_ratio(11000.0, 800.0, 9000.0) == pytest.approx(1.0)

    def test_clamps_below_idle(self):
        assert compute_ratio(0.0, 800.0, 9000.0) == pytest.approx(0.0)

    def test_zero_range_returns_zero(self):
        assert compute_ratio(9000.0, 9000.0, 9000.0) == pytest.approx(0.0)


class TestLightsState:
    def test_not_connected_all_unlit(self):
        assert lights_state(0.9, connected=False) == [COLOR_UNLIT] * NUM_LIGHTS

    def test_zero_ratio_all_unlit(self):
        assert lights_state(0.0, connected=True) == [COLOR_UNLIT] * NUM_LIGHTS

    def test_returns_nine_lights(self):
        assert len(lights_state(0.5, connected=True)) == NUM_LIGHTS

    def test_first_green_appears_at_threshold(self):
        threshold = 1 * (SHIFT_RATIO / 9)        # ≈ 0.103
        assert lights_state(threshold - 0.001, connected=True)[0] == COLOR_UNLIT
        assert lights_state(threshold,         connected=True)[0] == COLOR_GREEN

    def test_first_yellow_appears_at_threshold(self):
        threshold = 4 * (SHIFT_RATIO / 9)        # ≈ 0.413
        colors = lights_state(threshold, connected=True)
        assert colors[3] == COLOR_YELLOW          # first yellow
        assert colors[2] == COLOR_GREEN           # last green still lit

    def test_first_red_appears_at_threshold(self):
        threshold = 7 * (SHIFT_RATIO / 9)        # ≈ 0.723
        colors = lights_state(threshold, connected=True)
        assert colors[6] == COLOR_RED             # first red
        assert colors[5] == COLOR_YELLOW          # last yellow still lit

    def test_flash_lights_unlit_below_shift(self):
        colors = lights_state(0.80, connected=True)   # below SHIFT_RATIO=0.93
        assert colors[7] == COLOR_UNLIT
        assert colors[8] == COLOR_UNLIT

    def test_at_shift_ratio_all_flash(self):
        assert lights_state(SHIFT_RATIO, connected=True) == [COLOR_FLASH] * NUM_LIGHTS

    def test_above_shift_ratio_all_flash(self):
        assert lights_state(0.99, connected=True) == [COLOR_FLASH] * NUM_LIGHTS


class TestTelemetryState:
    def test_initially_not_connected(self):
        state = TelemetryState()
        assert state.connected is False
        assert state.ratio == 0.0
        assert state._effective_max == 0.0

    def test_update_marks_connected(self):
        state = TelemetryState()
        state.update(5000.0, 800.0, 9000.0)
        assert state.connected is True

    def test_update_uses_reported_max_before_calibration(self):
        # 4900 < 9000 * 0.65 = 5850 → below activation threshold → uses reported max
        state = TelemetryState(cal_db={})
        state.update(4900.0, 800.0, 9000.0)
        assert state.ratio == pytest.approx(0.5)
        assert state._effective_max == 0.0

    def test_calibrates_on_upshift_at_high_rpm(self):
        # Peak at 8500 (> 65% of 11000), then upshift from gear 2 → 3
        state = TelemetryState(cal_db={})
        state.update(8500.0, 800.0, 11000.0, gear=2)   # peak = 8500
        state.update(4000.0, 800.0, 11000.0, gear=3)   # upshift → calibrate
        assert state._effective_max == pytest.approx(8500.0 * 1.03)

    def test_calibrates_after_stable_peak_at_limiter(self):
        # Fallback: plateau at high RPM when driver never upshifts
        state = TelemetryState(cal_db={})
        state.update(8500.0, 800.0, 11000.0, gear=1)   # peak = 8500
        state._peak_stable_since -= 0.5                 # fake 500ms stability
        state.update(8480.0, 800.0, 11000.0, gear=1)   # still near peak → calibrate
        assert state._effective_max > 0
        assert state.ratio >= SHIFT_RATIO

    def test_calibration_can_exceed_reported_max_rpm(self):
        # Cars where game underreports max_rpm: peak can exceed it
        state = TelemetryState(cal_db={})
        state.update(9500.0, 800.0, 7000.0, gear=2)   # current > reported max
        state.update(4000.0, 800.0, 7000.0, gear=3)   # upshift
        # effective_max should be based on observed peak, not capped at 7000
        assert state._effective_max > 7000.0

    def test_no_calibration_if_peak_below_activation(self):
        # 6000 < 11000 * 0.65 = 7150 → never calibrates even on upshift
        state = TelemetryState(cal_db={})
        state.update(6000.0, 800.0, 11000.0, gear=2)
        state.update(3000.0, 800.0, 11000.0, gear=3)  # upshift but peak too low
        assert state._effective_max == 0.0

    def test_calibration_persisted_and_restored_on_car_change(self):
        shared_db: dict[str, float] = {}
        state = TelemetryState(cal_db=shared_db)
        # Calibrate car A via upshift
        state.update(8500.0, 800.0, 9000.0, gear=2)
        state.update(4000.0, 800.0, 9000.0, gear=3)
        saved = state._effective_max
        assert saved > 0
        # Switch to car B then back to car A — calibration restores immediately
        state.update(5000.0, 800.0, 7000.0, gear=1)   # car B
        state.update(5000.0, 800.0, 9000.0, gear=1)   # back to car A
        assert state._effective_max == pytest.approx(saved)

    def test_check_timeout_no_effect_when_not_connected(self):
        state = TelemetryState()
        state.check_timeout(timeout_seconds=0.0)
        assert state.connected is False

    def test_check_timeout_disconnects_and_resets_calibration(self):
        state = TelemetryState()
        state.update(5000.0, 800.0, 9000.0)
        state._effective_max = 8500.0
        state._peak_rpm = 8500.0
        state._last_packet_time -= 3.0
        state.check_timeout(timeout_seconds=2.0)
        assert state.connected is False
        assert state._effective_max == 0.0
        assert state._peak_rpm == 0.0

    def test_check_timeout_no_effect_within_timeout(self):
        state = TelemetryState()
        state.update(5000.0, 800.0, 9000.0)
        state.check_timeout(timeout_seconds=2.0)
        assert state.connected is True

    def test_initially_gear_zero(self):
        state = TelemetryState()
        assert state.gear == 0

    def test_update_stores_gear(self):
        state = TelemetryState()
        state.update(5000.0, 800.0, 9000.0, gear=4)
        assert state.gear == 4

    def test_update_gear_default_zero(self):
        state = TelemetryState()
        state.update(5000.0, 800.0, 9000.0)
        assert state.gear == 0

    def test_electric_detected_when_idle_rpm_zero(self):
        state = TelemetryState(cal_db={})
        state.update(8000.0, 0.0, 20000.0)
        assert state.is_electric is True
        assert state.ratio == 0.0

    def test_ice_not_detected_as_electric(self):
        state = TelemetryState()
        state.update(5000.0, 800.0, 9000.0)
        assert state.is_electric is False