"""Schematic renderer: output files, test-point maps and the layout checks.

Every circuit is rendered once per session into a temporary folder; the same assertions run
on that fresh render and on the committed files in ``circuits/<id>/``.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest
from matplotlib import font_manager

from differential.circuits import schematics
from differential.circuits.library import CIRCUIT_IDS, get_circuit
from differential.config import CIRCUITS_DIR

SVG = "{http://www.w3.org/2000/svg}"
SUFFIXES = ("_schematic.svg", "_schematic.png", "_schematic_dark.svg", "_testpoints.json")


@pytest.fixture(scope="session")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Render every circuit once (a few seconds); ``render`` raises if any check fails."""
    out = tmp_path_factory.mktemp("schematics")
    schematics.render_all(out)
    return out


@pytest.fixture(params=["fresh", "committed"])
def outputs(request: pytest.FixtureRequest) -> Path:
    if request.param == "committed":
        return CIRCUITS_DIR
    folder: Path = request.getfixturevalue("rendered")
    return folder


def _paths(root: Path, cid: str) -> dict[str, Path]:
    return {suffix: root / cid / f"{cid}{suffix}" for suffix in SUFFIXES}


def _tp_map(root: Path, cid: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_paths(root, cid)["_testpoints.json"].read_text())
    return data


def _svg_texts(path: Path) -> set[str]:
    return {(t.text or "").strip() for t in ET.parse(path).getroot().iter(f"{SVG}text")}


@pytest.mark.parametrize("cid", CIRCUIT_IDS)
def test_output_files_exist(outputs: Path, cid: str) -> None:
    paths = _paths(outputs, cid)
    for path in paths.values():
        assert path.is_file() and path.stat().st_size > 0, path
    width, height = schematics.png_size(paths["_schematic.png"])
    assert width > 500 and height > 500
    for suffix in ("_schematic.svg", "_schematic_dark.svg"):
        assert ET.parse(paths[suffix]).getroot().tag == f"{SVG}svg"


@pytest.mark.parametrize("cid", CIRCUIT_IDS)
def test_every_test_point_is_inside_the_viewbox(outputs: Path, cid: str) -> None:
    circuit = get_circuit(cid)
    tp_map = _tp_map(outputs, cid)
    minx, miny, w, h = tp_map["viewBox"]
    assert (tp_map["width"], tp_map["height"]) == (w, h)
    assert set(tp_map["test_points"]) == {tp.id for tp in circuit.test_points}
    for tp in circuit.test_points:
        entry = tp_map["test_points"][tp.id]
        assert minx < entry["x"] < minx + w and miny < entry["y"] < miny + h, tp.id
        assert entry["hv"] is tp.hv and entry["node"] == tp.node


@pytest.mark.parametrize("cid", CIRCUIT_IDS)
def test_test_point_map_matches_the_drawn_markers(outputs: Path, cid: str) -> None:
    """The JSON coordinates are the marker centres in both SVGs (overlay alignment)."""
    tp_map = _tp_map(outputs, cid)
    paths = _paths(outputs, cid)
    for suffix in ("_schematic.svg", "_schematic_dark.svg"):
        view_box, markers = schematics.svg_geometry(paths[suffix].read_text())
        assert view_box == tp_map["viewBox"]
        assert set(markers) == set(tp_map["test_points"])
        for tp_id, (x, y) in markers.items():
            entry = tp_map["test_points"][tp_id]
            assert (x, y) == pytest.approx((entry["x"], entry["y"]), abs=0.01), tp_id


@pytest.mark.parametrize("cid", CIRCUIT_IDS)
def test_marker_colours_follow_the_hv_flag(outputs: Path, cid: str) -> None:
    root = ET.parse(_paths(outputs, cid)["_schematic.svg"]).getroot()
    groups = {g.attrib["id"][3:]: g for g in root.iter(f"{SVG}g")
              if g.attrib.get("id", "").startswith("tp-") and not g.attrib["id"].endswith("-dot")}
    for tp in get_circuit(cid).test_points:
        style = next(groups[tp.id].iter(f"{SVG}use")).attrib["style"]
        colour = schematics.HV_COLOR if tp.hv else schematics.LV_COLOR
        assert f"stroke: {colour}" in style, tp.id


@pytest.mark.parametrize("cid", CIRCUIT_IDS)
def test_every_component_ref_is_svg_text(outputs: Path, cid: str) -> None:
    paths = _paths(outputs, cid)
    for suffix in ("_schematic.svg", "_schematic_dark.svg"):
        texts = _svg_texts(paths[suffix])
        missing = [c.ref for c in get_circuit(cid).components if c.ref not in texts]
        assert not missing, f"{suffix}: {missing}"


@pytest.mark.parametrize("cid", CIRCUIT_IDS)
def test_dark_variant_is_light_on_transparent(outputs: Path, cid: str) -> None:
    light = _paths(outputs, cid)["_schematic.svg"].read_text()
    dark = _paths(outputs, cid)["_schematic_dark.svg"].read_text()
    assert "fill: #ffffff" in light and schematics.LIGHT.ink in light
    assert "fill: #ffffff" not in dark and schematics.LIGHT.ink not in dark
    assert "stroke: #e6e6e6" in dark


def test_committed_maps_match_a_fresh_render(rendered: Path) -> None:
    """The committed test-point maps are up to date with the layout code."""
    try:
        font_manager.findfont(font_manager.FontProperties(family="Inter"),
                              fallback_to_default=False)
    except ValueError:
        pytest.skip("the committed schematics were rendered with the Inter font")
    for cid in CIRCUIT_IDS:
        assert _tp_map(CIRCUITS_DIR, cid) == _tp_map(rendered, cid), (
            f"{cid}: stale; run python -m differential.circuits.schematics")


def test_topology_check_catches_wiring_mistakes() -> None:
    sh = schematics.Sheet(get_circuit("tone"), schematics.LIGHT)
    sh.part("R302", (0.0, 0.0), (0.0, -2.0), "right")  # bass_b -> ground
    sh.ground((0.0, -2.0))
    sh.part("C304", (3.0, 0.0), (3.0, -2.0), "right")  # treb_b -> ground
    sh.wire((0.0, 0.0), (3.0, 0.0))  # shorts bass_b to treb_b; C304 left floating
    _, errors = schematics.check_topology(sh)
    assert any("short between nodes ['bass_b', 'treb_b']" in e for e in errors)
    assert any("node '0' is drawn as 2 separate pieces" in e for e in errors)
    assert any(e.startswith("components not drawn") for e in errors)

