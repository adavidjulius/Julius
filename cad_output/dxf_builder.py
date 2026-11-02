"""DXF floor-plan generator for AutoCAD-compatible output.

Usage:
    python dxf_builder.py            # writes sample_floor_plan.dxf
    python dxf_builder.py spec.json  # writes output from a JSON spec

The spec format (all lengths in the drawing unit you choose, e.g. meters):
{
  "title": "Sample Floor Plan",
  "units": "m",
  "wall_thickness": 0.2,
  "rooms": [
     {"name": "Living Room", "x": 0, "y": 0, "w": 6, "h": 5},
     {"name": "Bedroom",     "x": 6, "y": 0, "w": 4, "h": 5}
  ],
  "doors":   [{"x": 3, "y": 0, "width": 0.9, "wall": "south"}],
  "windows": [{"x": 1, "y": 5, "width": 1.5, "wall": "north"}]
}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf.enums import TextEntityAlignment

LAYERS = {
    "WALLS":   {"color": 7},
    "DOORS":   {"color": 3},
    "WINDOWS": {"color": 4},
    "ROOMS":   {"color": 8},
    "TEXT":    {"color": 2},
    "DIMS":    {"color": 6},
}


def _setup_doc() -> ezdxf.document.Drawing:
    doc = ezdxf.new(dxfversion="R2010", setup=True)
    doc.units = ezdxf.units.M
    for name, meta in LAYERS.items():
        doc.layers.add(name=name, color=meta["color"])
    return doc


def _draw_wall_rect(msp, x: float, y: float, w: float, h: float, t: float) -> None:
    """Draw a rectangular room outline using a polyline of given wall thickness."""
    pts = [
        (x, y),
        (x + w, y),
        (x + w, y + h),
        (x, y + h),
        (x, y),
    ]
    msp.add_lwpolyline(pts, dxfattribs={"layer": "WALLS", "const_width": t})


def _draw_door(msp, x: float, y: float, width: float, wall: str) -> None:
    """Simple door: a leaf line plus a swing arc."""
    import math
    if wall in ("south", "north"):
        leaf = [(x, y), (x + width, y)]
        cx, cy = x, y
        start, end = 0, 90
    else:  # east / west
        leaf = [(x, y), (x, y + width)]
        cx, cy = x, y
        start, end = 0, 90
    msp.add_line(leaf[0], leaf[1], dxfattribs={"layer": "DOORS"})
    msp.add_arc(
        center=(cx, cy),
        radius=width,
        start_angle=start,
        end_angle=end,
        dxfattribs={"layer": "DOORS"},
    )


def _draw_window(msp, x: float, y: float, width: float, wall: str) -> None:
    """Window drawn as a double line across the wall."""
    offset = 0.05
    if wall in ("south", "north"):
        msp.add_line((x, y - offset), (x + width, y - offset), dxfattribs={"layer": "WINDOWS"})
        msp.add_line((x, y + offset), (x + width, y + offset), dxfattribs={"layer": "WINDOWS"})
    else:
        msp.add_line((x - offset, y), (x - offset, y + width), dxfattribs={"layer": "WINDOWS"})
        msp.add_line((x + offset, y), (x + offset, y + width), dxfattribs={"layer": "WINDOWS"})


def _label_room(msp, name: str, x: float, y: float, w: float, h: float) -> None:
    text = msp.add_text(
        name,
        height=max(0.15, min(w, h) * 0.06),
        dxfattribs={"layer": "TEXT"},
    )
    text.set_placement((x + w / 2.0, y + h / 2.0), align=TextEntityAlignment.MIDDLE_CENTER)


def _title_block(msp, title: str, units: str, extents: tuple[float, float]) -> None:
    """Simple title line below the drawing."""
    w, h = extents
    y = -1.0
    msp.add_text(
        f"{title}  |  units: {units}  |  {w:.2f} x {h:.2f}",
        height=0.25,
        dxfattribs={"layer": "TEXT"},
    ).set_placement((0, y), align=TextEntityAlignment.LEFT)


def build(spec: dict[str, Any], out_path: Path) -> Path:
    doc = _setup_doc()
    msp = doc.modelspace()

    wall_t = float(spec.get("wall_thickness", 0.2))
    rooms = spec.get("rooms", [])
    max_x = max((r["x"] + r["w"] for r in rooms), default=0.0)
    max_y = max((r["y"] + r["h"] for r in rooms), default=0.0)

    for room in rooms:
        _draw_wall_rect(msp, room["x"], room["y"], room["w"], room["h"], wall_t)
        _label_room(msp, room["name"], room["x"], room["y"], room["w"], room["h"])

    for d in spec.get("doors", []):
        _draw_door(msp, d["x"], d["y"], d.get("width", 0.9), d.get("wall", "south"))

    for win in spec.get("windows", []):
        _draw_window(msp, win["x"], win["y"], win.get("width", 1.5), win.get("wall", "north"))

    _title_block(msp, spec.get("title", "Floor Plan"), spec.get("units", "m"), (max_x, max_y))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(out_path)
    return out_path


def sample_spec() -> dict[str, Any]:
    return {
        "title": "Sample One-Bedroom Apartment",
        "units": "m",
        "wall_thickness": 0.2,
        "rooms": [
            {"name": "Living Room", "x": 0,   "y": 0, "w": 6.0, "h": 5.0},
            {"name": "Bedroom",     "x": 6.0, "y": 0, "w": 4.0, "h": 5.0},
            {"name": "Kitchen",     "x": 0,   "y": 5.0, "w": 4.0, "h": 3.0},
            {"name": "Bathroom",    "x": 4.0, "y": 5.0, "w": 2.0, "h": 3.0},
            {"name": "Hall",        "x": 6.0, "y": 5.0, "w": 4.0, "h": 3.0},
        ],
        "doors": [
            {"x": 5.0, "y": 0.0, "width": 0.9,  "wall": "south"},
            {"x": 6.0, "y": 2.0, "width": 0.9,  "wall": "east"},
            {"x": 3.5, "y": 5.0, "width": 0.8,  "wall": "north"},
            {"x": 4.5, "y": 5.0, "width": 0.7,  "wall": "north"},
        ],
        "windows": [
            {"x": 1.5, "y": 5.0, "width": 1.5, "wall": "north"},
            {"x": 7.0, "y": 5.0, "width": 1.2, "wall": "north"},
            {"x": 0.0, "y": 1.5, "width": 1.5, "wall": "west"},
            {"x": 10.0,"y": 1.5, "width": 1.5, "wall": "east"},
        ],
    }


import os
import shutil
import subprocess


def convert_to_dwg(dxf_path: Path) -> Path | None:
    """Convert DXF to true AutoCAD DWG format using dxf2dwg (LibreDWG) or ODA."""
    dwg_path = dxf_path.with_suffix(".dwg")

    # 1. Check for LibreDWG dxf2dwg
    dxf2dwg_bin = shutil.which("dxf2dwg") or "/opt/homebrew/bin/dxf2dwg"
    if os.path.exists(dxf2dwg_bin) or shutil.which("dxf2dwg"):
        try:
            cmd = [str(dxf2dwg_bin), "-y", str(dxf_path), "-o", str(dwg_path)]
            subprocess.run(cmd, capture_output=True, text=True)
            if dwg_path.exists():
                return dwg_path
        except Exception:
            pass

    # 2. Check for ODA File Converter
    for oda in (
        "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter",
        str(Path.home() / "Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"),
    ):
        if os.path.exists(oda) and os.access(oda, os.X_OK):
            try:
                cmd = [oda, str(dxf_path.parent), str(dxf_path.parent), "ACAD2010", "ACAD2018", "0", "1", dxf_path.name]
                subprocess.run(cmd, capture_output=True, text=True)
                if dwg_path.exists():
                    return dwg_path
            except Exception:
                pass

    return None


def main() -> int:
    here = Path(__file__).resolve().parent
    if len(sys.argv) > 1 and sys.argv[1] not in ("--sample", "sample"):
        spec_path = Path(sys.argv[1])
        spec = json.loads(spec_path.read_text())
        out = here / (spec_path.stem + ".dxf")
    else:
        spec = sample_spec()
        out = here / "sample_floor_plan.dxf"

    written = build(spec, out)
    print(f"wrote DXF: {written} ({written.stat().st_size} bytes)")
    dwg = convert_to_dwg(written)
    if dwg:
        print(f"wrote DWG: {dwg} ({dwg.stat().st_size} bytes)")
    else:
        print("Note: DWG converter not found. To convert to DWG, run: brew install libredwg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
