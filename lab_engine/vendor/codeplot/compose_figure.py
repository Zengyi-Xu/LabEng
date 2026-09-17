#!/usr/bin/env python3
"""
compose_figure.py — Compose multiple SVG sub-figures into one combined figure (pure vector)

Usage:
    python compose_figure.py                     # Read .codeplot_gallery by default
    python compose_figure.py a.svg b.svg c.svg   # Or specify SVG files (in given order)

All layout parameters are in the CONFIG block below; edit values and rerun:
  - Labels: font family, size, weight, color, position (four corners), background, style
  - Layout: "grid" (uniform panels) or "custom" (specify position/size per panel)
  - Output: SVG vector; if cairosvg is installed, also export PDF/PNG

Principle: each sub-figure SVG is embedded as a nested <svg x y width height viewBox> in a container SVG.
Fully vector, no rasterization; labels are added during composition, keeping sub-figure files clean.
"""

import os
import re
import sys
import json

# ════════════════════════════════════════════════════════════════
# CONFIG — layout parameters (edit here)
# ════════════════════════════════════════════════════════════════

# ── Output ──
OUTPUT_SVG = "combined_figure.svg"   # Output file name
EXPORT_PDF = False                   # Also export PDF (requires pip install cairosvg)
EXPORT_PNG = False                   # Also export PNG (requires cairosvg)
PNG_DPI = 300                        # PNG resolution
BACKGROUND = "white"                 # Combined figure background; None means transparent

# ── Labels (a)(b)(c) ──
LABEL_FONT_FAMILY = "Liberation Sans"          # Label font family, e.g. "Liberation Sans" / "Arial" / "Times New Roman"
LABEL_FONT_SIZE = 20                 # Font size (pt)
LABEL_FONT_WEIGHT = "bold"           # normal / bold
LABEL_COLOR = "black"
LABEL_STYLE = "lower"                # Label style: "lower" (a) / "upper" (A) / "number" (1)
LABEL_BRACKETS = True                # True → (a); False → a
LABEL_POSITION = "top-left"          # top-left / top-right / bottom-left / bottom-right
LABEL_OFFSET_X = 6                   # Horizontal distance from panel edge (pt)
LABEL_OFFSET_Y = 6                   # Vertical distance from panel edge (pt)
LABEL_BACKGROUND = True              # Add white background behind labels (clearer over complex figures)

# ── Layout mode: "grid" or "custom" ──
LAYOUT = "grid"

# Grid layout parameters (panels are uniformly sized and scaled to fit cells)
GRID_ROWS = 2
GRID_COLS = 2
PANEL_WIDTH = 420                    # Width of each cell (pt)
PANEL_HEIGHT = 320                   # Height of each cell (pt)
H_SPACING = 24                       # Column spacing (pt)
V_SPACING = 24                       # Row spacing (pt)
MARGIN = 20                          # Margin around combined figure (pt)

# Custom layout parameters (used when LAYOUT = "custom")
# One dict per figure: x, y are top-left coordinates (pt); w, h are display sizes (pt, scaled to fit)
# "label" can override automatic labels; set to None to omit the label for that panel
CUSTOM_PANELS = [
    {"x": 20,  "y": 20,  "w": 420, "h": 320},
    {"x": 460, "y": 20,  "w": 420, "h": 320},
    {"x": 20,  "y": 360, "w": 420, "h": 320},
    {"x": 460, "y": 360, "w": 420, "h": 320},
]

# ════════════════════════════════════════════════════════════════
# Composition logic below; usually no need to edit
# ════════════════════════════════════════════════════════════════


def load_svg_entry(path):
    """Read SVG file, return {viewBox, aspect, inner}; return None on failure"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None
    mv = re.search(r'viewBox="([^"]+)"', content)
    if mv:
        nums = [float(v) for v in mv.group(1).replace(",", " ").split()]
        if len(nums) == 4 and nums[2] > 0 and nums[3] > 0:
            vb, vb_w, vb_h = mv.group(1), nums[2], nums[3]
        else:
            return None
    else:
        # Fallback to width/height attributes when no viewBox is present
        mw = re.search(r'width="([\d.]+)', content)
        mh = re.search(r'height="([\d.]+)', content)
        if not (mw and mh):
            return None
        vb_w, vb_h = float(mw.group(1)), float(mh.group(1))
        vb = f"0 0 {vb_w} {vb_h}"
    try:
        start = content.index(">", content.index("<svg")) + 1
        inner = content[start:content.rindex("</svg>")]
    except ValueError:
        return None
    return {"vb": vb, "aspect": vb_w / vb_h, "inner": inner}


def default_gallery_svgs():
    """Return SVG paths from .codeplot_gallery in index order"""
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".codeplot_gallery")
    idx_path = os.path.join(base, "gallery_index.json")
    paths = []
    if os.path.exists(idx_path):
        try:
            with open(idx_path, "r", encoding="utf-8") as f:
                items = json.load(f).get("items", [])
            for it in items:
                p = it.get("svg_path", "")
                if p and os.path.exists(p):
                    paths.append(p)
        except Exception:
            pass
    if not paths and os.path.isdir(base):
        paths = sorted(
            os.path.join(base, f) for f in os.listdir(base)
            if f.lower().endswith(".svg") and f != "composed.svg"
        )
    return paths


def make_label(i):
    if LABEL_STYLE == "upper":
        s = chr(65 + i)
    elif LABEL_STYLE == "number":
        s = str(i + 1)
    else:
        s = chr(97 + i)
    return f"({s})" if LABEL_BRACKETS else s


def label_elements(label, px, py, pw, ph):
    """Generate SVG elements for labels (optional white background); px,py,pw,ph are panel display area"""
    fs = LABEL_FONT_SIZE
    if LABEL_POSITION.endswith("right"):
        lx = px + pw - LABEL_OFFSET_X
        anchor = "end"
    else:
        lx = px + LABEL_OFFSET_X
        anchor = "start"
    if LABEL_POSITION.startswith("bottom"):
        ly = py + ph - LABEL_OFFSET_Y          # baseline
    else:
        ly = py + LABEL_OFFSET_Y + fs          # baseline

    parts = []
    if LABEL_BACKGROUND:
        est_w = len(label) * fs * 0.62 + 6
        if anchor == "end":
            rx = lx - est_w + 3
        else:
            rx = lx - 3
        if LABEL_POSITION.startswith("bottom"):
            ry = ly - fs - 3
        else:
            ry = ly - fs - 3
        parts.append(
            f'<rect x="{rx:.2f}" y="{ry:.2f}" width="{est_w:.2f}" height="{fs + 6:.2f}" '
            f'fill="white" fill-opacity="0.75"/>'
        )
    parts.append(
        f'<text x="{lx:.2f}" y="{ly:.2f}" text-anchor="{anchor}" '
        f'font-family="{LABEL_FONT_FAMILY}" font-size="{fs}" '
        f'font-weight="{LABEL_FONT_WEIGHT}" fill="{LABEL_COLOR}">{label}</text>'
    )
    return "\n".join(parts)


def compute_layout(n):
    """Return (panels, total_w, total_h); panels is [{x,y,w,h,label}]"""
    if LAYOUT == "custom":
        if n > len(CUSTOM_PANELS):
            raise SystemExit(
                f"custom layout only defines {len(CUSTOM_PANELS)} positions, but there are {n} figures;"
                f"please add more entries to CUSTOM_PANELS")
        panels = []
        for i in range(n):
            p = dict(CUSTOM_PANELS[i])
            p.setdefault("label", make_label(i))
            panels.append(p)
        total_w = max(p["x"] + p["w"] for p in panels) + MARGIN
        total_h = max(p["y"] + p["h"] for p in panels) + MARGIN
        return panels, total_w, total_h

    # grid layout
    rows, cols = GRID_ROWS, GRID_COLS
    if rows * cols < n:
        raise SystemExit(f"grid {rows}×{cols} cannot hold {n} figures; adjust GRID_ROWS/COLS")
    panels = []
    for i in range(n):
        r, c = divmod(i, cols)
        panels.append({
            "x": MARGIN + c * (PANEL_WIDTH + H_SPACING),
            "y": MARGIN + r * (PANEL_HEIGHT + V_SPACING),
            "w": PANEL_WIDTH,
            "h": PANEL_HEIGHT,
            "label": make_label(i),
        })
    total_w = MARGIN * 2 + cols * PANEL_WIDTH + (cols - 1) * H_SPACING
    total_h = MARGIN * 2 + rows * PANEL_HEIGHT + (rows - 1) * V_SPACING
    return panels, total_w, total_h


def compose(svg_paths, out_path):
    entries = []
    for p in svg_paths:
        e = load_svg_entry(p)
        if e is None:
            print(f"[warn] parse failed, skipped: {p}")
        else:
            entries.append(e)
    if not entries:
        raise SystemExit("No usable SVG sub-figures")

    panels, total_w, total_h = compute_layout(len(entries))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{total_w:.1f}pt" height="{total_h:.1f}pt" '
        f'viewBox="0 0 {total_w:.2f} {total_h:.2f}">',
    ]
    if BACKGROUND:
        parts.append(f'<rect width="100%" height="100%" fill="{BACKGROUND}"/>')

    for e, p in zip(entries, panels):
        # Scale proportionally to fit cell and center
        if p["w"] / p["h"] > e["aspect"]:
            dh = p["h"]
            dw = dh * e["aspect"]
        else:
            dw = p["w"]
            dh = dw / e["aspect"]
        ox = p["x"] + (p["w"] - dw) / 2
        oy = p["y"] + (p["h"] - dh) / 2
        parts.append(
            f'<svg x="{ox:.2f}" y="{oy:.2f}" width="{dw:.2f}" height="{dh:.2f}" '
            f'viewBox="{e["vb"]}">{e["inner"]}</svg>'
        )
        if p.get("label"):
            parts.append(label_elements(p["label"], ox, oy, dw, dh))

    parts.append("</svg>")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return total_w, total_h


def export_extra(svg_path):
    """Optional: export PDF/PNG with cairosvg"""
    try:
        import cairosvg
    except ImportError:
        print("[info] cairosvg not installed, skipping PDF/PNG export (pip install cairosvg to enable)")
        return
    base = os.path.splitext(svg_path)[0]
    if EXPORT_PDF:
        cairosvg.svg2pdf(url=svg_path, write_to=base + ".pdf")
        print(f"Exported: {base}.pdf")
    if EXPORT_PNG:
        cairosvg.svg2png(url=svg_path, write_to=base + ".png", dpi=PNG_DPI)
        print(f"Exported: {base}.png")


def main():
    svg_paths = sys.argv[1:] or default_gallery_svgs()
    if not svg_paths:
        raise SystemExit(
            "No sub-figure SVG found. Please run codeplot.py and add to gallery first,"
            "or specify manually: python compose_figure.py a.svg b.svg ...")
    print(f"Total: {len(svg_paths)} sub-figures | layout: {LAYOUT}")
    w, h = compose(svg_paths, OUTPUT_SVG)
    print(f"Generated: {OUTPUT_SVG}  ({w:.0f} × {h:.0f} pt)")
    if EXPORT_PDF or EXPORT_PNG:
        export_extra(OUTPUT_SVG)


if __name__ == "__main__":
    main()
