import tempfile
from pathlib import Path
from config import (Config, load_config, save_config,
                    RPM_STYLES, BRAKE_STYLES, GEAR_STYLES, SHIFT_STYLES,
                    STYLE_LABELS)


def _roundtrip(cfg: Config) -> Config:
    with tempfile.NamedTemporaryFile(suffix=".ini", delete=False) as f:
        p = Path(f.name)
    save_config(p, cfg)
    loaded = load_config(p)
    p.unlink(missing_ok=True)
    return loaded


def test_style_defaults_survive_roundtrip():
    cfg = Config()
    out = _roundtrip(cfg)
    assert out.rpm_style      == "dot_row"
    assert out.brake_style    == "horiz_bar"
    assert out.throttle_style == "horiz_bar"
    assert out.gear_style     == "box"
    assert out.shift_up_style == "triangle"
    assert out.shift_dn_style == "triangle"


def test_non_default_style_survives_roundtrip():
    cfg = Config(rpm_style="arc_gauge", gear_style="hexagon", shift_up_style="pulse_ring")
    out = _roundtrip(cfg)
    assert out.rpm_style      == "arc_gauge"
    assert out.gear_style     == "hexagon"
    assert out.shift_up_style == "pulse_ring"


def test_invalid_style_falls_back_to_default():
    with tempfile.NamedTemporaryFile(suffix=".ini", delete=False, mode="w") as f:
        f.write("[styles]\nrpm = not_a_real_style\n")
        p = Path(f.name)
    out = load_config(p)
    p.unlink(missing_ok=True)
    assert out.rpm_style == Config().rpm_style


def test_layout_defaults_survive_roundtrip():
    cfg = Config()
    out = _roundtrip(cfg)
    assert out.rpm_w == 500
    assert out.gear_h == 60
    assert out.shift_up_h == 32


def test_custom_layout_survives_roundtrip():
    cfg = Config(rpm_x=100, rpm_y=50, gear_x=800, gear_y=200)
    out = _roundtrip(cfg)
    assert out.rpm_x == 100
    assert out.rpm_y == 50
    assert out.gear_x == 800


def test_all_style_names_are_in_labels():
    all_styles = RPM_STYLES + BRAKE_STYLES + GEAR_STYLES + SHIFT_STYLES
    for s in all_styles:
        assert s in STYLE_LABELS, f"Missing label for style '{s}'"


def test_base_element_imports_and_has_edit_colors():
    import importlib
    base_mod = importlib.import_module("elements.base")
    assert hasattr(base_mod, "BaseElement")
    assert "rpm" in base_mod._EDIT_COLORS
    assert "shift_up" in base_mod._EDIT_COLORS
    assert len(base_mod._EDIT_COLORS) == 6
