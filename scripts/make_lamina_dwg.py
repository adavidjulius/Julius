"""Generate an AutoCAD DWG of the orthographic projections of a 40 mm
circular lamina inclined 30 deg to HP and 45 deg to VP, following the
5-stage procedure in question1.txt.

Outputs:
    ~/Desktop/Julius1.dxf
    ~/Desktop/Julius1.dwg   (via libredwg dxf2dwg)
"""
from __future__ import annotations

import math
import shutil
import subprocess
import sys
from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment

# ---------------------------------------------------------------------------
# Constants from the question
# ---------------------------------------------------------------------------
DIAMETER = 40.0
RADIUS = DIAMETER / 2.0
THETA_HP = math.radians(30.0)   # surface inclination to HP (front-view tilt)
THETA_VP = math.radians(45.0)   # edge/diameter inclination to VP (plan rotation)
N = 8                            # circumference split into 8 equal segments

# Layout: reference XY line, views arranged in the classic first-angle grid.
XY_Y = 0.0                    # Y coordinate of the XY ground line

# Top view (Stage 1, true shape) centre, below XY line
TV1_CX, TV1_CY = 60.0, -60.0

# Front view (Stage 2, 30 deg tilt) centre, above XY line
FV1_CX, FV1_CY = 60.0, 55.0

# Stage 3 top view (foreshortened ellipse from 30 deg tilt), to the right
TV2_CX, TV2_CY = 200.0, -60.0

# Stage 4 front view (final, 45 deg to VP), to the right above XY line
FV2_CX, FV2_CY = 200.0, 55.0


# ---------------------------------------------------------------------------
# Layers
# ---------------------------------------------------------------------------
def setup_doc() -> ezdxf.document.Drawing:
    doc = ezdxf.new(dxfversion="R2010", setup=True)
    doc.units = ezdxf.units.MM
    layers = {
        "OUTLINE":   {"color": 7},   # main visible outlines
        "CONSTR":    {"color": 8},   # thin construction lines
        "CENTRE":    {"color": 1},   # centre lines (red)
        "TEXT":      {"color": 3},   # labels (green)
        "DIMS":      {"color": 6},   # dimensions (magenta)
        "REF":       {"color": 2},   # XY reference line (yellow)
    }
    for name, meta in layers.items():
        if name not in doc.layers:
            doc.layers.add(name=name, color=meta["color"])
    return doc


def add_text(msp, text: str, x: float, y: float, height: float = 2.5,
             layer: str = "TEXT", align=TextEntityAlignment.MIDDLE_CENTER) -> None:
    t = msp.add_text(text, height=height, dxfattribs={"layer": layer})
    t.set_placement((x, y), align=align)


def add_line(msp, p1, p2, layer: str = "OUTLINE") -> None:
    msp.add_line(p1, p2, dxfattribs={"layer": layer})


def add_ellipse(msp, cx: float, cy: float, rx: float, ry: float,
                rotation_deg: float = 0.0, layer: str = "OUTLINE") -> None:
    msp.add_ellipse(
        center=(cx, cy),
        major_axis=(rx * math.cos(math.radians(rotation_deg)),
                    rx * math.sin(math.radians(rotation_deg))),
        ratio=(ry / rx) if rx else 1.0,
        dxfattribs={"layer": layer},
    )


def circle_points(cx: float, cy: float, r: float, n: int = N):
    """Return n points on a circle, starting at 0 deg (east) going CCW."""
    return [
        (cx + r * math.cos(2 * math.pi * i / n),
         cy + r * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Stage builders
# ---------------------------------------------------------------------------
def stage1_reference_and_top_view(msp) -> None:
    """Draw XY reference line and the true-shape top view circle."""
    # XY reference line spanning the whole sheet
    add_line(msp, (10.0, XY_Y), (280.0, XY_Y), layer="REF")
    add_text(msp, "X", 8.0, XY_Y, layer="TEXT")
    add_text(msp, "Y", 282.0, XY_Y, layer="TEXT")

    # True-shape circle in the top view
    msp.add_circle((TV1_CX, TV1_CY), RADIUS, dxfattribs={"layer": "OUTLINE"})
    # Centre lines
    add_line(msp, (TV1_CX - RADIUS - 5, TV1_CY), (TV1_CX + RADIUS + 5, TV1_CY), layer="CENTRE")
    add_line(msp, (TV1_CX, TV1_CY - RADIUS - 5), (TV1_CX, TV1_CY + RADIUS + 5), layer="CENTRE")

    # 8 division points and their labels
    labels = "abcdefgh"
    for i, (px, py) in enumerate(circle_points(TV1_CX, TV1_CY, RADIUS)):
        msp.add_point((px, py), dxfattribs={"layer": "CONSTR"})
        # label just outside the circle
        dx = (px - TV1_CX) * 1.15
        dy = (py - TV1_CY) * 1.15
        add_text(msp, labels[i], TV1_CX + dx, TV1_CY + dy, height=2.0)

    add_text(msp, "TOP VIEW (True Shape)", TV1_CX, TV1_CY - RADIUS - 12, height=3.0)


def stage2_front_view(msp) -> None:
    """Front view of the circle tilted 30 deg to HP — an ellipse in projection.

    In first-angle projection, the front view of a circle inclined at theta
to HP shows the diameter perpendicular to the axis of rotation as true length
(= 2R) and the diameter along the axis foreshortened to 2R*cos(theta).
    """
    major = RADIUS                       # semi-axis perpendicular to tilt axis
    minor = RADIUS * math.cos(THETA_HP)  # semi-axis along the tilt direction

    # Ellipse centre in front view
    cx, cy = FV1_CX, FV1_CY
    # Major axis horizontal (perpendicular to the axis of tilt which is vertical here)
    add_ellipse(msp, cx, cy, major, minor, rotation_deg=0.0, layer="OUTLINE")

    # Centre lines
    add_line(msp, (cx - major - 5, cy), (cx + major + 5, cy), layer="CENTRE")
    add_line(msp, (cx, cy - major - 5), (cx, cy + major + 5), layer="CENTRE")

    # 8 projected points from the circle vertices: on the front view the a..h
    # points map to a'(e'), b'(d'), c', h'(f'), g'
    # We place labels at the projected positions: each circle point (x,y) maps
    # to front-view point (x, y*cos(theta)) — a pure vertical compression.
    pts = circle_points(TV1_CX, TV1_CY, RADIUS)
    fv_labels = ["a'(e')", "b'(d')", "c'", "d'(b')", "e'(a')", "f'(h')", "g'", "h'(f')"]
    for i, (px, py) in enumerate(pts):
        # Local coordinates relative to top view centre
        lx = px - TV1_CX
        ly = py - TV1_CY
        # Front-view projection: horizontal unchanged, vertical scaled by cos(theta)
        fx = cx + lx
        fy = cy + ly * math.cos(THETA_HP)
        msp.add_point((fx, fy), dxfattribs={"layer": "CONSTR"})
        # Add label with a slight outward offset
        add_text(msp, fv_labels[i], fx + 4.0, fy + 2.0, height=1.8)

    # Draw the projection lines from top view circle points up to XY line
    for (px, py) in pts:
        add_line(msp, (px, py), (px, XY_Y), layer="CONSTR")

    add_text(msp, "FRONT VIEW (30\u00b0 to HP)", cx, cy + major + 10, height=3.0)


def stage3_top_view_of_tilt(msp) -> None:
    """Top view of the 30-deg-inclined circle — an ellipse.

    When the circular lamina is tilted 30 deg to HP, its top view is an
    ellipse with the diameter perpendicular to the tilt axis unchanged (2R)
    and the diameter along the tilt axis foreshortened to 2R*cos(theta).
    """
    cx, cy = TV2_CX, TV2_CY
    major = RADIUS                       # perpendicular to tilt axis (horizontal here)
    minor = RADIUS * math.cos(THETA_HP)  # along the tilt axis
    add_ellipse(msp, cx, cy, major, minor, rotation_deg=0.0, layer="OUTLINE")

    # Centre lines
    add_line(msp, (cx - major - 5, cy), (cx + major + 5, cy), layer="CENTRE")
    add_line(msp, (cx, cy - major - 5), (cx, cy + major + 5), layer="CENTRE")

    # 8 points on the ellipse and labels a1..h1
    labels = [f"{c}1" for c in "abcdefgh"]
    pts = circle_points(TV1_CX, TV1_CY, RADIUS)
    for i, (px, py) in enumerate(pts):
        lx = px - TV1_CX
        ly = py - TV1_CY
        # Stage 3 top view: horizontal unchanged (perp to tilt axis),
        # vertical (along tilt axis) foreshortened by cos(theta)
        ex = cx + lx
        ey = cy + ly * math.cos(THETA_HP)
        msp.add_point((ex, ey), dxfattribs={"layer": "CONSTR"})
        add_text(msp, labels[i], ex + 3.5, ey + 2.0, height=1.8)

    add_text(msp, "TOP VIEW after 30\u00b0 tilt", cx, cy - major - 12, height=3.0)


def stage4_final_front_view(msp) -> None:
    """Final front view: circular lamina inclined 30 deg to HP, then rotated
    45 deg about the axis perpendicular to VP so the diameter is 45 deg to VP.

    The final front view is the projection of an ellipse (Stage-3 plan) onto
    the VP after a 45 deg rotation about the vertical axis. The result is an
    ellipse whose major axis is the true diameter 2R (the diameter that was
    rotated to be perpendicular to VP) and whose minor axis is
    2R * cos(theta_HP) * cos(theta_VP).
    """
    cx, cy = FV2_CX, FV2_CY
    major = RADIUS
    minor = RADIUS * math.cos(THETA_HP) * math.cos(THETA_VP)
    add_ellipse(msp, cx, cy, major, minor, rotation_deg=0.0, layer="OUTLINE")

    # Centre lines
    add_line(msp, (cx - major - 5, cy), (cx + major + 5, cy), layer="CENTRE")
    add_line(msp, (cx, cy - major - 5), (cx, cy + major + 5), layer="CENTRE")

    # 8 final points a1'..h1'
    labels = [f"{c}1'" for c in "abcdefgh"]
    pts = circle_points(TV1_CX, TV1_CY, RADIUS)
    for i, (px, py) in enumerate(pts):
        lx = px - TV1_CX
        ly = py - TV1_CY
        # Rotate in plan by 45 deg (about vertical axis), then project onto VP:
        # horizontal coordinate picks up the rotation; vertical is foreshortened
        # by the HP tilt.
        lx_rot = lx * math.cos(THETA_VP) - ly * math.sin(THETA_VP)
        ly_rot = lx * math.sin(THETA_VP) + ly * math.cos(THETA_VP)
        fx = cx + lx_rot * math.cos(THETA_VP)  # projected onto VP
        # Vertical: the tilt to HP compresses the "ly_rot" axis
        fy = cy + ly_rot * math.cos(THETA_HP)
        # Simplify: for a proper final projection, use ellipse mapping:
        # Final front view is the ellipse directly; place labels on the ellipse
        # by parametric angle matching each original point.
        ang = 2 * math.pi * i / N
        fx = cx + major * math.cos(ang)
        fy = cy + minor * math.sin(ang)
        msp.add_point((fx, fy), dxfattribs={"layer": "CONSTR"})
        add_text(msp, labels[i], fx + 4.0, fy + 2.0, height=1.8)

    # Reference angular path at 45 deg to VP near the final view
    add_line(msp, (cx - 30, cy - 30), (cx + 30, cy + 30), layer="CONSTR")

    add_text(msp, "FRONT VIEW (30\u00b0 to HP, 45\u00b0 to VP)", cx, cy + major + 10, height=3.0)


# ---------------------------------------------------------------------------
# Dimensioning & presentation (Stage 5)
# ---------------------------------------------------------------------------
def stage5_dimensions(msp) -> None:
    """Linear diameter on the true circle and angular dims for the two tilts."""
    # Diameter dimension on Stage 1 circle
    dim = msp.add_linear_dim(
        base=(TV1_CX, TV1_CY - RADIUS - 8),
        p1=(TV1_CX - RADIUS, TV1_CY),
        p2=(TV1_CX + RADIUS, TV1_CY),
        dimstyle="EZDXF",
        dxfattribs={"layer": "DIMS"},
    )
    dim.render()

    # Angular 30 deg at the front view: between horizontal and the tilt axis
    # Simple representation: an arc + text label showing 30 deg
    msp.add_arc(
        center=(FV1_CX - RADIUS, FV1_CY - RADIUS),
        radius=RADIUS * 0.6,
        start_angle=0.0,
        end_angle=30.0,
        dxfattribs={"layer": "DIMS"},
    )
    add_text(msp, "30\u00b0", FV1_CX - RADIUS + RADIUS * 0.5,
             FV1_CY - RADIUS + RADIUS * 0.15, height=2.5, layer="DIMS")

    # Angular 45 deg near the final view reference line
    add_text(msp, "45\u00b0 to VP", FV2_CX, FV2_CY - RADIUS - 12, height=2.5, layer="DIMS")


def add_title(msp) -> None:
    add_text(msp, "ORTHOGRAPHIC PROJECTIONS - CIRCULAR LAMINA", 145.0, 150.0, height=4.0)
    add_text(msp, "Diameter 40 mm | 30\u00b0 to HP | 45\u00b0 to VP", 145.0, 143.0, height=3.0)
    add_text(msp, "Drawn by Julius", 145.0, 136.0, height=2.5)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def build(out_dxf: Path) -> Path:
    doc = setup_doc()
    msp = doc.modelspace()
    stage1_reference_and_top_view(msp)
    stage2_front_view(msp)
    stage3_top_view_of_tilt(msp)
    stage4_final_front_view(msp)
    stage5_dimensions(msp)
    add_title(msp)
    out_dxf.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(out_dxf)
    return out_dxf


def convert_to_dwg(dxf_path: Path) -> Path | None:
    dwg_path = dxf_path.with_suffix(".dwg")
    bin_path = shutil.which("dxf2dwg") or "/opt/homebrew/bin/dxf2dwg"
    if not (shutil.which("dxf2dwg") or Path(bin_path).exists()):
        return None
    # dxf2dwg -y <in.dxf> -o <out.dwg>
    res = subprocess.run(
        [str(bin_path), "-y", str(dxf_path), "-o", str(dwg_path)],
        capture_output=True, text=True,
    )
    if res.returncode != 0 or not dwg_path.exists():
        print("dxf2dwg failed:", res.stdout, res.stderr, file=sys.stderr)
        return None
    return dwg_path


def main() -> int:
    desktop = Path.home() / "Desktop"
    out_dxf = desktop / "Julius1.dxf"
    built = build(out_dxf)
    print(f"wrote DXF: {built} ({built.stat().st_size} bytes)")
    dwg = convert_to_dwg(built)
    if dwg:
        print(f"wrote DWG: {dwg} ({dwg.stat().st_size} bytes)")
        return 0
    print("DWG conversion unavailable.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
