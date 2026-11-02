# CAD Output

AutoCAD-compatible drawings produced by Julius.

## Files

- `dxf_builder.py` — Python generator. Takes a JSON spec or falls back to a built-in sample.
- `sample_floor_plan.dxf` — working demo (one-bedroom apartment, 10 m x 8 m, layered).
- `dxf_to_dwg.sh` — wrapper that drives the free ODA File Converter to emit a true `.dwg`.

## Open the sample

- **AutoCAD**: `File > Open` → `sample_floor_plan.dxf`. To get a native DWG: `File > Save As > AutoCAD Drawing (*.dwg)`.
- **LibreCAD** (free, Mac): opens DXF and can `File > Export > DWG`.
- **Fusion 360 / Revit**: imports DXF directly.

## Regenerate or make a new drawing

```bash
.venv/bin/python cad_output/dxf_builder.py                  # sample
.venv/bin/python cad_output/dxf_builder.py my_spec.json     # custom
```

Spec format (all lengths in the drawing unit you pick, e.g. meters):

```json
{
  "title": "My Plan",
  "units": "m",
  "wall_thickness": 0.2,
  "rooms":   [{"name": "Living", "x": 0, "y": 0, "w": 6, "h": 5}],
  "doors":   [{"x": 3, "y": 0, "width": 0.9, "wall": "south"}],
  "windows": [{"x": 1, "y": 5, "width": 1.5, "wall": "north"}]
}
```

## True DWG output

True native `.dwg` generation is supported automatically via `libredwg` (`dxf2dwg` installed via Homebrew):

```bash
# Automatically creates BOTH sample_floor_plan.dxf and sample_floor_plan.dwg:
.venv/bin/python cad_output/dxf_builder.py

# Or convert any DXF to DWG manually:
./cad_output/dxf_to_dwg.sh cad_output/sample_floor_plan.dxf
```

That writes `sample_floor_plan.dwg` next to the DXF.

## Open in AutoCAD

- **AutoCAD**: Double-click or `File > Open` → `sample_floor_plan.dwg` (or `.dxf`).
- **LibreCAD / Fusion 360 / Revit**: Open/Import directly.
