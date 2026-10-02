#!/usr/bin/env python3
"""graph — lightweight stunning graphs. Pure stdlib. No deps.
Usage:
  python graph.py flow examples/flow_decision.yaml -o out/flow.html
  python graph.py arch examples/arch.yaml -o out/arch.html
  python graph.py scatter examples/scatter.csv --x dose --y expr -o out/scatter.html
Outputs self-contained .html (hero) + .svg sidecar.
"""
import argparse, csv, html, json, os, sys

try:
    import yaml  # optional; falls back to JSON if missing
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

THEME = {
    "paper": "#f5f5f5", "ink": "#2d3142", "muted": "#4f5d75",
    "soft": "#7a8399", "rule": "rgba(45,49,66,0.12)",
    "accent": "#eb6c36", "accent_tint": "rgba(235,108,54,0.08)",
    "link": "#2e5aa8", "card": "#ffffff",
}
THEMES = {
    "editorial": dict(THEME),
    "ink": {"paper": "#2d3142", "ink": "#f5f5f5", "muted": "#bfc0c0",
            "soft": "#8e98ac", "rule": "rgba(245,245,245,0.14)",
            "accent": "#f08a59", "accent_tint": "rgba(240,138,89,0.12)",
            "link": "#6a95d8", "card": "#393e53"},
    "print": {"paper": "#ffffff", "ink": "#111111", "muted": "#444444",
              "soft": "#777777", "rule": "rgba(0,0,0,0.18)",
              "accent": "#000000", "accent_tint": "rgba(0,0,0,0.06)",
              "link": "#333333", "card": "#ffffff"},
}
OKABE_ITO_DARK = ["#56B4E9", "#E69F00", "#2dd4a7", "#CC79A7", "#7cc7ff", "#f08a59", "#F0E442", "#e8e8e8"]


def get_theme(name=None, path=None):
    """Resolve a theme dict: builtin name + optional JSON overrides file."""
    t = dict(THEMES.get(name or "editorial", THEMES["editorial"]))
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                custom = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            sys.exit(f"bad --theme-file: {e}")
        unknown = sorted(set(custom) - set(t))
        if unknown:
            sys.exit(f"--theme-file unknown keys {unknown}; known: {sorted(t)}")
        t.update(custom)
        if not name:
            name = "custom"
    t["_name"] = name or "editorial"
    return t


def series_palette(t):
    """Colorblind-safe series colors fitting the theme (dark gets brightened set)."""
    return OKABE_ITO_DARK if t.get("_name") == "ink" else OKABE_ITO


def _humanize(col):
    """p99_latency_ms -> p99 latency ms. Acronyms uppercased, units kept short."""
    out = []
    for w in str(col).replace("_", " ").split():
        low = w.lower()
        if low in ("p50", "p90", "p95", "p99", "ms", "rps", "pct"):
            out.append(low)
        elif len(w) <= 3 and w.isalpha() and low not in ("per", "avg", "max", "min"):
            out.append(w.upper())
        else:
            out.append(w.capitalize())
    return " ".join(out)


def _with_unit(label, unit):
    """Append (unit) unless the label already carries it: 'p99 ms'+'ms' -> 'p99 (ms) x1."""
    label, unit = (label or "").strip(), (unit or "").strip()
    if not unit:
        return label
    low = label.lower()
    if low.endswith(f"({unit.lower()})") or low.endswith(f" {unit.lower()}") or low.endswith(f"_{unit.lower()}"):
        label = label[: -len(unit) - 1].rstrip(" (_-") if not low.endswith(f"({unit.lower()})") else label
        if low.endswith(f"({unit.lower()})"):
            return label
    return f"{label} ({unit})" if label else f"({unit})"


def _wrap(text, width=24, max_lines=3):
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if len(trial) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(0, width - 1)] + "…"
    return lines


def render_pincallout(t, px, py, text, above=True, top=None):
    """In-plot journal callout: masked italic label + leader dot on the point."""
    lines = _wrap(text, 26, 2)
    w = max([len(l) for l in lines] + [4]) * 6.8 + 16
    h = 12 + 15 * len(lines)
    ty = py - 12 - h if above else py + 12
    if top is not None:
        ty = max(ty, top)
    yo = py + (-4 if above else 4)
    s = [f'<line x1="{px:.1f}" y1="{yo:.1f}" x2="{px:.1f}" y2="{(ty + h) if above else ty:.1f}" stroke="{t["soft"]}" stroke-width="1"/>',
         f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3" fill="{t["accent"]}"/>',
         f'<rect x="{px - w/2:.1f}" y="{ty:.1f}" width="{w:.1f}" height="{h:.1f}" rx="3" fill="{t["card"]}" stroke="{t["rule"]}" stroke-width="1"/>']
    for j, ln in enumerate(lines):
        s.append(f'<text x="{px:.1f}" y="{ty + 16 + j*15:.1f}" font-size="11.5" font-style="italic" font-family="{SERIF}" fill="{t["ink"]}" text-anchor="middle">{esc(ln)}</text>')
    return "\n".join(s)


def render_noterail(t, notes, rail_x, top, lh=92):
    """Right-rail editorial callouts: italic serif note + thin leader to (ax, ay).
    notes = [(ax, ay, text)]. Caller widens canvas by 200 when notes exist."""
    s = []
    for i, (ax, ay, text) in enumerate(notes):
        ry = top + 14 + i * lh
        tx = rail_x + 14
        s.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{tx:.1f}" y2="{ry:.1f}" stroke="{t["soft"]}" stroke-width="1"/>')
        s.append(f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="2.5" fill="{t["accent"]}"/>')
        for j, ln in enumerate(_wrap(text)):
            s.append(f'<text x="{tx:.1f}" y="{ry + 4 + j * 16:.1f}" font-size="13" font-style="italic" font-family="{SERIF}" fill="{t["ink"]}">{esc(ln)}</text>')
    return "\n".join(s)
OKABE_ITO = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442", "#000000"]
FONT = "system-ui, 'Segoe UI', sans-serif"
SANS = MONO = SERIF = FONT

HTML_SHELL = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
body{{margin:0;background:{paper};color:{ink};font-family:{font}}}
.gbar{{display:flex;gap:.4rem;align-items:center;padding:.4rem .7rem;background:{paper};border-bottom:1px solid {rule}}}
.gbar button{{font:13px {font};color:{ink};background:{card};border:1px solid {rule};padding:.28rem .6rem;cursor:pointer}}
svg{{display:block;max-width:100%;height:auto;margin:0 auto}}
@media print{{.gbar{{display:none}} body{{background:#fff}}}}
</style></head><body>
<div class="gbar" id="gbar">
  <button type="button" id="copy">Copy SVG</button>
  <button type="button" id="save">Export SVG</button>
  <button type="button" id="png">Export PNG</button>
</div>
{svg}
<script>
(function(){{
  var svg = document.querySelector("svg");
  if (!svg) return;
  function svgText(){{ return new XMLSerializer().serializeToString(svg); }}
  document.getElementById("copy").addEventListener("click", function(){{
    var btn = this;
    navigator.clipboard.writeText(svgText()).then(function(){{
      btn.textContent = "Copied"; setTimeout(function(){{ btn.textContent = "Copy SVG"; }}, 900);
    }});
  }});
  document.getElementById("save").addEventListener("click", function(){{
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([svgText()], {{type: "image/svg+xml"}}));
    a.download = "graph.svg"; a.click();
  }});
  document.getElementById("png").addEventListener("click", function(){{
    var btn = this;
    var vb = svg.viewBox.baseVal;
    var w = (vb && vb.width) ? vb.width : svg.getBoundingClientRect().width;
    var h = (vb && vb.height) ? vb.height : svg.getBoundingClientRect().height;
    var url = URL.createObjectURL(new Blob([svgText()], {{type: "image/svg+xml;charset=utf-8"}}));
    var img = new Image();
    img.onload = function(){{
      var c = document.createElement("canvas");
      c.width = Math.max(1, Math.round(w * 2));
      c.height = Math.max(1, Math.round(h * 2));
      var g = c.getContext("2d");
      g.fillStyle = getComputedStyle(document.body).backgroundColor || "#ffffff";
      g.fillRect(0, 0, c.width, c.height);
      g.drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      c.toBlob(function(b){{
        var a = document.createElement("a");
        a.href = URL.createObjectURL(b);
        a.download = "graph.png";
        a.click();
        btn.textContent = "Saved";
        setTimeout(function(){{ btn.textContent = "Export PNG"; }}, 900);
      }}, "image/png");
    }};
    img.onerror = function(){{
      URL.revokeObjectURL(url);
      btn.textContent = "PNG failed";
      setTimeout(function(){{ btn.textContent = "Export PNG"; }}, 1200);
    }};
    img.src = url;
  }});
}})();
</script>
</body></html>"""


def esc(s):
    return html.escape(str(s))


def figure_heading(t, title, subtitle, x=28):
    """Title and subtitle drawn on the figure. Returns (svg bits, block height)."""
    bits, y = [], 8
    if title:
        y += 18
        bits.append(
            f'<text x="{x}" y="{y}" font-size="18" font-weight="600" font-family="{FONT}" fill="{t["ink"]}">{esc(title)}</text>')
    if subtitle:
        y += 18
        bits.append(
            f'<text x="{x}" y="{y}" font-size="13" font-family="{FONT}" fill="{t["muted"]}">{esc(subtitle)}</text>')
    return bits, ((y + 16) if bits else 8)


def _hit(highlights, *vals):
    want = {str(h) for h in (highlights or [])}
    return any(str(v) in want for v in vals if v is not None)


def load_spec(path):
    with open(path, encoding="utf-8") as f:
        txt = f.read()
    if path.endswith(".json"):
        return json.loads(txt)
    if HAS_YAML and path.endswith((".yaml", ".yml")):
        return yaml.safe_load(txt)
    # minimal fallback: JSON in .yaml also works
    try:
        return json.loads(txt)
    except Exception:
        sys.exit(f"{path}: need PyYAML for YAML (pip install pyyaml) or use JSON")


def markers(t):
    def one(mid, fill):
        # userSpaceOnUse keeps the head a fixed size, so direction stays readable on a thin stroke
        return (f'<marker id="{mid}" markerWidth="12" markerHeight="9" refX="11" refY="4.5" '
                f'orient="auto" markerUnits="userSpaceOnUse">'
                f'<polygon points="0 0,12 4.5,0 9" fill="{fill}"/></marker>')
    return "<defs>" + one("a", t["muted"]) + one("aa", t["accent"]) + one("al", t["link"]) + one("ar", t["soft"]) + "</defs>"


def elbow(x1, y1, x2, y2, r=8):
    """Rounded orthogonal path between (x1,y1)->(x2,y2)."""
    if x1 == x2 or y1 == y2:
        return f"M{x1},{y1} L{x2},{y2}"
    mx = x2 if abs(x2 - x1) < 60 else (x1 + x2) / 2
    # horizontal then vertical with rounded corner
    sx = 1 if x2 > mx else -1
    sy = 1 if y2 > y1 else -1
    return (f"M{x1},{y1} L{mx - sx*r},{y1} Q{mx},{y1} {mx},{y1 + sy*r} L{mx},{y2 - sy*r} "
            f"Q{mx},{y2} {mx + sx*r},{y2} L{x2},{y2}")


def axis_ticks(vmin, vmax, n=5):
    """Nice ticks with one spare step above vmax so a bar and its label stay inside the plot."""
    ticks = nice_ticks(vmin, vmax, n=n)
    if len(ticks) < 2:
        step = (vmax - vmin) or 1
        return [round(vmin, 10), round(vmin + step, 10)]
    if vmax >= ticks[-1] - 1e-9:
        step = ticks[-1] - ticks[-2] or 1
        ticks = list(ticks) + [round(ticks[-1] + step, 10)]
    return ticks


def bar_path(x, y, w, h, rx, cap="top"):
    """Bar path. The end on the baseline is square; only the free end is rounded.
    cap is 'top' or 'bottom' (vertical) or 'right' or 'left' (horizontal)."""
    if w <= 0 or h <= 0:
        return ""
    rx = 0 if rx <= 0 else min(float(rx), w / 2.0, h / 2.0)
    if rx <= 0.01:
        return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"'
    x2, y2 = x + w, y + h
    if cap == "top":
        d = (f"M{x:.1f},{y2:.1f} L{x:.1f},{y+rx:.1f} Q{x:.1f},{y:.1f} {x+rx:.1f},{y:.1f} "
             f"L{x2-rx:.1f},{y:.1f} Q{x2:.1f},{y:.1f} {x2:.1f},{y+rx:.1f} L{x2:.1f},{y2:.1f} Z")
    elif cap == "bottom":
        d = (f"M{x:.1f},{y:.1f} L{x:.1f},{y2-rx:.1f} Q{x:.1f},{y2:.1f} {x+rx:.1f},{y2:.1f} "
             f"L{x2-rx:.1f},{y2:.1f} Q{x2:.1f},{y2:.1f} {x2:.1f},{y2-rx:.1f} L{x2:.1f},{y:.1f} Z")
    elif cap == "left":
        d = (f"M{x2:.1f},{y:.1f} L{x+rx:.1f},{y:.1f} Q{x:.1f},{y:.1f} {x:.1f},{y+rx:.1f} "
             f"L{x:.1f},{y2-rx:.1f} Q{x:.1f},{y2:.1f} {x+rx:.1f},{y2:.1f} L{x2:.1f},{y2:.1f} Z")
    else:
        d = (f"M{x:.1f},{y:.1f} L{x2-rx:.1f},{y:.1f} Q{x2:.1f},{y:.1f} {x2:.1f},{y+rx:.1f} "
             f"L{x2:.1f},{y2-rx:.1f} Q{x2:.1f},{y2:.1f} {x2-rx:.1f},{y2:.1f} L{x:.1f},{y2:.1f} Z")
    return f'<path d="{d}"'


_SIDE = {"n": (0.0, -1.0), "s": (0.0, 1.0), "e": (1.0, 0.0), "w": (-1.0, 0.0)}


def _node_box(node):
    sh = (node or {}).get("shape", "rect")
    if sh == "dot":
        return sh, 4.0, 4.0
    if sh == "diamond":
        return sh, 80.0, 32.0
    return "box", 80.0, 28.0


def node_side(cx, cy, node, tx, ty):
    """Side of the node that faces (tx, ty)."""
    sh, hw, hh = _node_box(node)
    if sh == "dot":
        return "s"
    dx, dy = tx - cx, ty - cy
    if abs(dx) <= hw and abs(dy) > abs(dx):
        return "s" if dy > 0 else "n"
    if abs(dy) <= hh and abs(dx) >= abs(dy):
        return "e" if dx > 0 else "w"
    if abs(dx) >= abs(dy):
        return "e" if dx >= 0 else "w"
    return "s" if dy >= 0 else "n"


def port_on(cx, cy, node, side, along=0.0):
    """Point on a side. along slides it so two arrows do not share one pixel.
    A lone diamond exit stays on the vertex (along 0)."""
    sh, hw, hh = _node_box(node)
    if sh == "dot":
        return cx, cy
    vx, vy = _SIDE[side]
    tx, ty = -vy, vx
    lim = 12.0 if sh == "diamond" else max(8.0, (hh if side in ("e", "w") else hw) - 10.0)
    along = max(-lim, min(lim, along))
    return cx + vx * hw + tx * along, cy + vy * hh + ty * along


def node_port(cx, cy, node, tx, ty):
    """Center of the side facing (tx, ty). Diamond vertices and box edge-centers, never the node interior."""
    side = node_side(cx, cy, node, tx, ty)
    x, y = port_on(cx, cy, node, side, 0.0)
    return x, y, side


def _slots(n, lo, hi):
    """n positions inside [lo, hi], centered, at most 22px apart."""
    if n <= 1:
        return [(lo + hi) / 2.0]
    span = hi - lo
    gap = min(22.0, span / (n - 1))
    width = gap * (n - 1)
    start = (lo + hi) / 2.0 - width / 2.0
    return [start + i * gap for i in range(n)]


def assign_ports(pos, edges):
    """Spread arrows along a side. Outgoing and incoming on the same side get opposite halves,
    so a return arrow does not leave from the pixel it arrived on."""
    sides = []
    buckets = {}
    for i, e in enumerate(edges):
        if e.get("from") not in pos or e.get("to") not in pos:
            sides.append(None)
            continue
        x1, y1, n1 = pos[e["from"]]
        x2, y2, n2 = pos[e["to"]]
        s1 = node_side(x1, y1, n1, x2, y2)
        s2 = node_side(x2, y2, n2, x1, y1)
        sides.append((s1, s2))
        k_out = y2 if s1 in ("e", "w") else x2
        k_in = y1 if s2 in ("e", "w") else x1
        buckets.setdefault((e["from"], s1), []).append((i, "out", k_out))
        buckets.setdefault((e["to"], s2), []).append((i, "in", k_in))
    along = {}
    for (nid, side), items in buckets.items():
        sh, hw, hh = _node_box(pos[nid][2])
        lim = 0.0 if sh in ("diamond", "dot") else max(8.0, (hh if side in ("e", "w") else hw) - 10.0)
        outs = sorted((it for it in items if it[1] == "out"), key=lambda t: t[2])
        ins = sorted((it for it in items if it[1] == "in"), key=lambda t: t[2])
        if sh == "diamond" and len(items) > 1:
            ordered = outs + ins
            for (ei, role, _), v in zip(ordered, _slots(len(ordered), -10.0, 10.0)):
                along[(ei, role)] = v
            continue
        if outs and ins and lim >= 8:
            for (ei, role, _), v in zip(outs, _slots(len(outs), -lim, -6.0)):
                along[(ei, role)] = v
            for (ei, role, _), v in zip(ins, _slots(len(ins), 6.0, lim)):
                along[(ei, role)] = v
        else:
            group = outs + ins
            vals = [0.0] * len(group) if lim < 1 else _slots(len(group), -lim, lim)
            for (ei, role, _), v in zip(group, vals):
                along[(ei, role)] = v
    out = {}
    for i, e in enumerate(edges):
        if sides[i] is None:
            continue
        s1, s2 = sides[i]
        x1, y1, n1 = pos[e["from"]]
        x2, y2, n2 = pos[e["to"]]
        ax, ay = port_on(x1, y1, n1, s1, along.get((i, "out"), 0.0))
        bx, by = port_on(x2, y2, n2, s2, along.get((i, "in"), 0.0))
        out[i] = (ax, ay, s1, bx, by, s2)
    return out


def _tail(x, y, side, col):
    """Dot on the outgoing stub so the start of the arrow is not only an arrowhead at the far end."""
    vx, vy = _SIDE.get(side, (0.0, 1.0))
    return f'<circle cx="{x + vx * 7:.1f}" cy="{y + vy * 7:.1f}" r="2.7" fill="{col}"/>'


def _round_poly(pts, r=8):
    clean = []
    for p in pts:
        if not clean or abs(p[0] - clean[-1][0]) > 0.4 or abs(p[1] - clean[-1][1]) > 0.4:
            clean.append((float(p[0]), float(p[1])))
    pruned = []
    for i, p in enumerate(clean):
        if 0 < i < len(clean) - 1:
            x0, y0 = pruned[-1]
            x1, y1 = p
            x2, y2 = clean[i + 1]
            if (abs(x0 - x1) < 0.4 and abs(x1 - x2) < 0.4) or (abs(y0 - y1) < 0.4 and abs(y1 - y2) < 0.4):
                continue
        pruned.append(p)
    if len(pruned) < 2:
        return ""
    if len(pruned) == 2:
        (x1, y1), (x2, y2) = pruned
        return f"M{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}"
    d = [f"M{pruned[0][0]:.1f},{pruned[0][1]:.1f}"]
    for i in range(1, len(pruned) - 1):
        x0, y0 = pruned[i - 1]
        x1, y1 = pruned[i]
        x2, y2 = pruned[i + 1]
        l1 = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 or 1.0
        l2 = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 or 1.0
        rr = min(r, l1 / 2.0, l2 / 2.0)
        ax, ay = x1 - (x1 - x0) / l1 * rr, y1 - (y1 - y0) / l1 * rr
        bx, by = x1 + (x2 - x1) / l2 * rr, y1 + (y2 - y1) / l2 * rr
        d.append(f"L{ax:.1f},{ay:.1f} Q{x1:.1f},{y1:.1f} {bx:.1f},{by:.1f}")
    d.append(f"L{pruned[-1][0]:.1f},{pruned[-1][1]:.1f}")
    return " ".join(d)


def route_edge(x1, y1, side1, x2, y2, side2, r=8, stub=16, nudge=0):
    """Leave one side-center, arrive at the other. Returns path, label x/y, label-is-vertical.
    nudge shifts a sideways corridor so a return arrow does not sit on the outbound one."""
    vx, vy = _SIDE[side1]
    ux, uy = _SIDE[side2]
    ax, ay = x1 + vx * stub, y1 + vy * stub
    bx, by = x2 + ux * stub, y2 + uy * stub
    pts = [(x1, y1), (ax, ay)]
    leave_h = side1 in ("e", "w")
    enter_h = side2 in ("e", "w")
    if leave_h and enter_h:
        if abs(ay - by) >= 0.5:
            lo, hi = sorted((ax, bx))
            mx = min(max((ax + bx) / 2.0 + nudge, lo + 8), hi - 8)
            pts += [(mx, ay), (mx, by)]
        pts.append((bx, by))
    elif (not leave_h) and (not enter_h):
        if abs(ax - bx) >= 0.5:
            my = (ay + by) / 2.0
            pts += [(ax, my), (bx, my)]
        pts.append((bx, by))
    elif leave_h and not enter_h:
        pts += [(x2, ay), (bx, by)]
    else:
        pts += [(ax, y2), (bx, by)]
    pts.append((x2, y2))
    best, mx, my, vert = 0.0, (x1 + x2) / 2.0, (y1 + y2) / 2.0, False
    for (px, py), (qx, qy) in zip(pts, pts[1:]):
        length = abs(qx - px) + abs(qy - py)
        if length > best:
            best = length
            mx, my = (px + qx) / 2.0, (py + qy) / 2.0
            vert = abs(qy - py) > abs(qx - px)
    return _round_poly(pts, r), mx, my, vert


def edge_ends(pos, src_id, dst_id):
    x1, y1, n1 = pos[src_id]
    x2, y2, n2 = pos[dst_id]
    px, py, s1 = node_port(x1, y1, n1, x2, y2)
    qx, qy, s2 = node_port(x2, y2, n2, x1, y1)
    return px, py, s1, qx, qy, s2


def corner_rx(corners):
    return {"sharp": 0, "rounded": 10, "editorial": 6}.get(corners, 6)


def node_box(t, x, y, w, h, name, sub="", tag="", focal=False, corners="editorial"):
    fill = t["accent_tint"] if focal else t["card"]
    stroke = t["accent"] if focal else t["ink"]
    rx = corner_rx(corners)
    cx = x + w / 2
    s = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{t["paper"]}"/>',
         f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}"/>']
    if tag:
        s.append(f'<rect x="{x+8}" y="{y+6}" width="{max(28,len(tag)*7)}" height="12" rx="2" fill="none" stroke="{stroke}" stroke-opacity=".4" stroke-width=".8"/>')
        s.append(f'<text x="{x+8+max(28,len(tag)*7)/2}" y="{y+15}" font-size="8" font-family="{FONT}" fill="{stroke}" text-anchor="middle">{esc(tag)}</text>')
    s.append(f'<text x="{cx}" y="{y+h/2+2}" font-size="12" font-weight="600" font-family="{SANS}" fill="{t["ink"]}" text-anchor="middle">{esc(name)}</text>')
    if sub:
        s.append(f'<text x="{cx}" y="{y+h/2+18}" font-size="9" font-family="{MONO}" fill="{t["muted"]}" text-anchor="middle">{esc(sub)}</text>')
    return "\n".join(s)


def diamond(t, cx, cy, w, h, name, focal=False):
    stroke = t["accent"] if focal else t["ink"]
    fill = t["accent_tint"] if focal else t["card"]
    pts = f"{cx},{cy-h/2} {cx+w/2},{cy} {cx},{cy+h/2} {cx-w/2},{cy}"
    return (f'<polygon points="{pts}" fill="{t["paper"]}"/>'
            f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}"/>'
            f'<text x="{cx}" y="{cy+4}" font-size="12" font-weight="600" font-family="{SANS}" fill="{t["ink"]}" text-anchor="middle">{esc(name)}</text>')


def _pill_w(text):
    return max(40, int(len(text) * 6.4 + 12))


def arrow_label(t, mx, ay, text, vertical=False):
    """Label sitting off the shaft, on the paper, so it does not cut the arrow."""
    w = _pill_w(text)
    if vertical:
        return (f'<rect x="{mx+8}" y="{ay-9}" width="{w}" height="16" rx="2" fill="{t["paper"]}"/>'
                f'<text x="{mx+8+w/2}" y="{ay+3}" font-size="10" font-family="{MONO}" fill="{t["muted"]}" text-anchor="middle">{esc(text)}</text>')
    return (f'<rect x="{mx-w/2}" y="{ay-24}" width="{w}" height="16" rx="2" fill="{t["paper"]}"/>'
            f'<text x="{mx}" y="{ay-12}" font-size="10" font-family="{MONO}" fill="{t["muted"]}" text-anchor="middle">{esc(text)}</text>')


def nice_ticks(vmin, vmax, n=5):
    """Pretty tick positions (Heckbert nice numbers)."""
    import math
    if vmin == vmax:
        vmax = vmin + 1
    span = vmax - vmin
    step0 = span / n
    mag = 10 ** math.floor(math.log10(step0))
    for m in (1, 2, 2.5, 5, 10):
        if step0 / mag <= m:
            step = m * mag
            break
    lo = math.floor(vmin / step) * step
    ticks, v = [], lo
    while v <= vmax + 1e-9 and len(ticks) < 12:
        ticks.append(round(v, 10))
        v += step
    if ticks and ticks[-1] < vmax - 1e-9 and len(ticks) < 12:
        ticks.append(round(ticks[-1] + step, 10))  # axis must cover the data
    return ticks


def fmt_tick(v):
    if v == int(v) and abs(v) < 10000:
        return str(int(v))
    if abs(v) >= 1000:
        return f"{v/1000:g}k"
    return f"{v:g}"


def auto_ranks(nodes, edges):
    """Longest-path layering (Sugiyama layer assignment only): sources rank 0,
    rank(v) = max(rank(pred)+1). Cycles broken by DFS visit order. Pure stdlib."""
    ids = [n["id"] for n in nodes]
    preds = {i: [] for i in ids}
    for e in edges:
        if e.get("from") in preds and e.get("to") in preds and e["from"] != e["to"]:
            preds[e["to"]].append(e["from"])
    rank, visiting = {}, set()

    def visit(nid, depth=0):
        if nid in rank:
            return rank[nid]
        if nid in visiting or depth > len(ids):
            return 0  # cycle guard
        visiting.add(nid)
        r = max([visit(p, depth + 1) + 1 for p in preds[nid]], default=0)
        visiting.discard(nid)
        rank[nid] = r
        return r

    for nid in ids:
        visit(nid)
    return rank


def render_flow(spec, corners="editorial", auto=False, theme=None):
    t = theme or THEME
    nodes = spec["nodes"]  # [{id,shape,name,tag?,sub?,focal?}]
    edges = spec.get("edges", [])  # [{from,to,label?,focal?}]
    _notes = (spec.get("notes", []) or [])[:2]
    head_bits, head_h = figure_heading(t, spec.get("title") or "", spec.get("sub") or "", x=30)
    W, col_w, top, gap_y = (720 + (200 if _notes else 0)), 200, max(90, head_h + 20), 120
    if auto or not any("rank" in n for n in nodes):
        computed = auto_ranks(nodes, edges)
        ranks = {n["id"]: computed.get(n["id"], 0) for n in nodes}
    else:
        ranks = {}
    pos = {}
    # rank = explicit, else list order, else longest-path; shared ranks fan out
    # across x unless explicit 'lane' (-1 left|0 center|1 right) is given
    by_rank = {}
    for i, n in enumerate(nodes):
        rk = n.get("rank", ranks.get(n["id"], i))
        by_rank.setdefault(rk, []).append(n)
    maxrk = max(by_rank) if by_rank else 0
    placed = {}  # id -> cx, filled rank by rank for barycenter ordering
    for rk in sorted(by_rank):
        group = by_rank[rk]
        if len(group) > 1 and not any("lane" in g for g in group):
            # barycenter heuristic: order by mean predecessor x (fewer crossings)
            def _bary(n):
                xs = [placed[e["from"]] for e in edges
                      if e.get("to") == n["id"] and e["from"] in placed]
                return sum(xs) / len(xs) if xs else len(placed)
            for j, n in enumerate(sorted(group, key=_bary)):
                cx = W / 2 + (j - (len(group) - 1) / 2) * 200
                pos[n["id"]] = (cx, top + rk * gap_y + 30, n)
                placed[n["id"]] = cx
        else:
            for n in group:
                lane = n.get("lane", 0)
                cx = W / 2 + lane * (col_w + 40)
                pos[n["id"]] = (cx, top + rk * gap_y + 30, n)
                placed[n["id"]] = cx
    low = max((cy for _, cy, _ in pos.values()), default=top)
    if _notes:
        low = max(low, top + 14 + max(0, len(_notes) - 1) * 92 + 52)
    H = int(low + 112)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" viewBox="0 0 {W} {H}" width="{W}"><title>{esc(spec.get("title","flow"))}</title>',
             f'<desc>{esc(spec.get("sub", spec.get("title", "flow")))}</desc>',
             f'<rect width="{W}" height="{H}" fill="{t["paper"]}"/>', markers(t)]
    parts.extend(head_bits)
    for nid, (cx, cy, n) in pos.items():
        sh = n.get("shape", "rect")
        if sh == "diamond":
            parts.append(diamond(t, cx, cy, 160, 64, n["name"], n.get("focal", False)))
        elif sh == "oval":
            parts.append(node_box(t, cx-80, cy-28, 160, 56, n["name"], n.get("sub",""), n.get("tag",""), n.get("focal",False), corners).replace(f'rx="{corner_rx(corners)}"','rx="20"', 1))
        elif sh == "dot":
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="4" fill="{t["ink"]}"/>')
        else:
            parts.append(node_box(t, cx-80, cy-28, 160, 56, n["name"], n.get("sub",""), n.get("tag",""), n.get("focal",False), corners))
    # edges after nodes. Ports are spread so an input and an output do not share a point.
    ports = assign_ports(pos, edges)
    for i, e in enumerate(edges):
        if i not in ports:
            continue
        x1, y1, s1, x2, y2, s2 = ports[i]
        col = t["accent"] if e.get("focal") else t["muted"]
        mid = "aa" if e.get("focal") else "a"
        nudge = label_dy = 0
        if s1 in ("e", "w") and s2 in ("e", "w") and y1 > y2 + 24:
            nudge = -20 if x1 <= x2 else 20
            label_dy = -34
        d, lx, ly, vertical = route_edge(x1, y1, s1, x2, y2, s2, nudge=nudge)
        if not d:
            continue
        parts.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="1.8" marker-end="url(#{mid})"/>')
        parts.append(_tail(x1, y1, s1, col))
        if e.get("label"):
            parts.append(arrow_label(t, lx, ly + label_dy, e["label"].upper(), vertical=vertical))
    if _notes:
        rail = []
        for nt in _notes:
            if nt.get("at") in pos:
                cx, cy, _n = pos[nt["at"]]
                rail.append((cx + 80, cy, nt["text"]))
        parts.append(render_noterail(t, rail, W - 186, top))
    # legend strip
    ly = H - 40
    parts.append(f'<line x1="30" y1="{ly-8}" x2="{W-30}" y2="{ly-8}" stroke="{t["rule"]}" stroke-width=".8"/>')
    parts.append(f'<text x="30" y="{ly+8}" font-size="11" font-family="{FONT}" fill="{t["muted"]}">rect = step, diamond = decision, oval = start or end</text>')
    parts.append("</svg>")
    return "\n".join(parts), W, H


def render_arch(spec, corners="editorial", theme=None):
    t = theme or THEME
    nodes = spec["nodes"]; edges = spec.get("edges", [])
    _notes = (spec.get("notes", []) or [])[:2]
    head_bits, head_h = figure_heading(t, spec.get("title") or "", spec.get("sub") or "", x=30)
    W = 760 + (200 if _notes else 0)
    # simple layered: group by 'layer' (0 top..n), spread across width
    from collections import defaultdict
    layers = defaultdict(list)
    for n in nodes:
        layers[n.get("layer", 0)].append(n)
    pos = {}
    top, gap_y = max(100, head_h + 24), 140
    for li, key in enumerate(sorted(layers)):
        row = layers[key]
        for j, n in enumerate(row):
            x = (W / (len(row)+1)) * (j+1)
            y = top + li * gap_y
            pos[n["id"]] = (x, y, n)
    low = max((y for _, y, _ in pos.values()), default=top)
    if _notes:
        low = max(low, top + 14 + max(0, len(_notes) - 1) * 92 + 52)
    H = int(low + 112)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" viewBox="0 0 {W} {H}" width="{W}"><title>{esc(spec.get("title","arch"))}</title>',
             f'<desc>{esc(spec.get("sub", spec.get("title", "arch")))}</desc>',
             f'<rect width="{W}" height="{H}" fill="{t["paper"]}"/>', markers(t)]
    parts.extend(head_bits)
    for nid,(x,y,n) in pos.items():
        parts.append(node_box(t, x-80, y-28, 160, 56, n["name"], n.get("sub",""), n.get("tag",""), n.get("focal",False), corners))
    ports = assign_ports(pos, edges)
    for i, e in enumerate(edges):
        if i not in ports:
            continue
        x1, y1, s1, x2, y2, s2 = ports[i]
        col = t["link"] if e.get("proto","").startswith("http") else (t["accent"] if e.get("focal") else t["muted"])
        dash = ' stroke-dasharray="5,4"' if e.get("async") else ""
        mid = "al" if e.get("proto", "").startswith("http") else ("aa" if e.get("focal") else "a")
        d, lx, ly, vertical = route_edge(x1, y1, s1, x2, y2, s2)
        if not d:
            continue
        parts.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="1.8"{dash} marker-end="url(#{mid})"/>')
        parts.append(_tail(x1, y1, s1, col))
        if e.get("label"):
            parts.append(arrow_label(t, lx, ly, e["label"].upper(), vertical=vertical))
    if _notes:
        rail = []
        for nt in _notes:
            if nt.get("at") in pos:
                x, y, _n = pos[nt["at"]]
                rail.append((x + 80, y, nt["text"]))
        parts.append(render_noterail(t, rail, W - 186, top))
    ly = H - 40
    parts.append(f'<line x1="30" y1="{ly-8}" x2="{W-30}" y2="{ly-8}" stroke="{t["rule"]}" stroke-width=".8"/>')
    parts.append(f'<text x="30" y="{ly+8}" font-size="11" font-family="{FONT}" fill="{t["muted"]}">blue = http, dashed = async, coral = focal</text>')
    parts.append("</svg>")
    return "\n".join(parts), W, H


def render_seq(spec, corners="editorial", theme=None):
    t = theme or THEME
    actors = spec.get("actors", [])
    messages = spec.get("messages", [])
    n_act = max(1, len(actors))
    margin_x = 70
    _notes = (spec.get("notes", []) or [])[:2]
    head_bits, head_h = figure_heading(t, spec.get("title") or "", spec.get("sub") or "", x=30)
    longest = 48
    for m in messages:
        if m.get("from") == m.get("to"):
            continue
        lbl = m.get("label") or ""
        if m.get("proto"):
            lbl = f"[{m['proto'].upper()}] {lbl}"
        longest = max(longest, _pill_w(lbl.upper()))
    pitch = max(180, longest + 36)
    W = margin_x * 2 + max(0, n_act - 1) * pitch + 140 + (200 if _notes else 0)
    pos = {}
    for i, a in enumerate(actors):
        cx = margin_x + 70 + i * pitch
        pos[a["id"]] = (cx, a)
    top = max(90, head_h + 16)
    msg_gap = 52
    msg_start = top + 74
    H = msg_start + len(messages) * msg_gap + 80
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" viewBox="0 0 {W} {H}" width="{W}"><title>{esc(spec.get("title","sequence"))}</title>',
             f'<desc>{esc(spec.get("sub", spec.get("title", "sequence")))}</desc>',
             f'<rect width="{W}" height="{H}" fill="{t["paper"]}"/>', markers(t)]
    parts.extend(head_bits)
    # Lifelines
    for aid, (cx, a) in pos.items():
        parts.append(f'<line x1="{cx:.1f}" y1="{top+52}" x2="{cx:.1f}" y2="{H-50}" stroke="{t["rule"]}" stroke-width="1.2" stroke-dasharray="4,4"/>')
    # Messages
    for i, m in enumerate(messages):
        f_id = m.get("from")
        t_id = m.get("to")
        if f_id not in pos or t_id not in pos:
            continue
        x1, _ = pos[f_id]
        x2, _ = pos[t_id]
        my = msg_start + i * msg_gap
        focal = m.get("focal", False)
        is_http = m.get("proto", "").startswith("http")
        col = t["accent"] if focal else (t["link"] if is_http else t["muted"])
        mid = "aa" if focal else ("al" if is_http else "a")
        dash = ' stroke-dasharray="4,4"' if (m.get("reply") or m.get("async")) else ''
        if f_id == t_id:
            # Self-call loop
            lw = 32
            parts.append(f'<path d="M{x1:.1f},{my} L{x1+lw:.1f},{my} L{x1+lw:.1f},{my+20} L{x1+4:.1f},{my+20}" fill="none" stroke="{col}" stroke-width="1.5"{dash} marker-end="url(#{mid})"/>')
            if m.get("label"):
                parts.append(arrow_label(t, x1 + lw + max(20, len(m["label"])*3.5), my + 10, m["label"].upper()))
        else:
            direction = 1 if x2 >= x1 else -1
            x_from = x1 + direction * 8
            x_to = x2 - direction * 8
            parts.append(f'<line x1="{x_from:.1f}" y1="{my}" x2="{x_to:.1f}" y2="{my}" stroke="{col}" stroke-width="1.6"{dash} marker-end="url(#{mid})"/>')
            if m.get("label"):
                lbl = m["label"]
                if m.get("proto"):
                    lbl = f"[{m['proto'].upper()}] {lbl}"
                parts.append(arrow_label(t, (x1 + x2) / 2, my, lbl.upper()))
    # Actor boxes at top
    for aid, (cx, a) in pos.items():
        bw, bh = 140, 52
        bx, by = cx - bw / 2, top
        parts.append(node_box(t, bx, by, bw, bh, a["name"], a.get("sub", ""), a.get("tag", ""), a.get("focal", False), corners))
    if _notes:
        rail = []
        for nt in _notes:
            if nt.get("at") in pos:
                cx, _a = pos[nt["at"]]
                rail.append((cx + 70, top + 26, nt["text"]))
        parts.append(render_noterail(t, rail, W - 186, top))
    # Legend
    ly = H - 28
    parts.append(f'<line x1="30" y1="{ly-10}" x2="{W-30}" y2="{ly-10}" stroke="{t["rule"]}" stroke-width=".8"/>')
    parts.append(f'<text x="30" y="{ly+4}" font-size="11" font-family="{FONT}" fill="{t["muted"]}">solid = sync, dashed = reply or async, blue = http, coral = focal</text>')
    parts.append("</svg>")
    return "\n".join(parts), W, H


def render_schema(spec, corners="editorial", theme=None):
    t = theme or THEME
    tables = spec.get("tables", [])
    relations = spec.get("relations", [])
    head_bits, head_h = figure_heading(t, spec.get("title") or "", spec.get("sub") or "", x=30)
    base_y = max(90, head_h + 16)
    rx = corner_rx(corners)
    tbl_w, row_h = 240, 24
    col_gap, row_gap = 70, 60
    max_cols = 3 if len(tables) >= 3 else max(1, len(tables))
    table_boxes = {}
    for i, tbl in enumerate(tables):
        cols = tbl.get("columns", [])
        h = 44 + len(cols) * row_h + 12
        if "x" in tbl and "y" in tbl:
            x, y = tbl["x"], tbl["y"]
        else:
            grid_c = i % max_cols
            grid_r = i // max_cols
            x = 60 + grid_c * (tbl_w + col_gap)
            y = base_y + grid_r * (260 + row_gap)
        col_y_map = {}
        for c_idx, c in enumerate(cols):
            col_y_map[c["name"]] = y + 44 + c_idx * row_h + row_h / 2
        table_boxes[tbl["id"]] = {"x": x, "y": y, "w": tbl_w, "h": h, "col_y_map": col_y_map, "tbl": tbl}
    max_x = max((b["x"] + b["w"] for b in table_boxes.values()), default=760)
    max_y = max((b["y"] + b["h"] for b in table_boxes.values()), default=400)
    _notes = (spec.get("notes", []) or [])[:2]
    if _notes:
        max_y = max(max_y, 110 + 14 + max(0, len(_notes) - 1) * 92 + 52)
    W = max(780, int(max_x + 60)) + (200 if _notes else 0)
    H = int(max_y + 72)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" viewBox="0 0 {W} {H}" width="{W}"><title>{esc(spec.get("title","schema"))}</title>',
             f'<desc>{esc(spec.get("sub", spec.get("title", "schema")))}</desc>',
             f'<rect width="{W}" height="{H}" fill="{t["paper"]}"/>', markers(t)]
    parts.extend(head_bits)
    # Relations (rendered behind table cards)
    for rel in relations:
        from_id, to_id = rel.get("from"), rel.get("to")
        if from_id not in table_boxes or to_id not in table_boxes:
            continue
        b1, b2 = table_boxes[from_id], table_boxes[to_id]
        from_col, to_col = rel.get("from_col"), rel.get("to_col")
        y1 = b1["col_y_map"].get(from_col, b1["y"] + b1["h"] / 2)
        y2 = b2["col_y_map"].get(to_col, b2["y"] + b2["h"] / 2)
        if b1["x"] + b1["w"] <= b2["x"]:
            x1, x2 = b1["x"] + b1["w"], b2["x"] - 6
        elif b2["x"] + b2["w"] <= b1["x"]:
            x1, x2 = b1["x"], b2["x"] + b2["w"] + 6
        else:
            x1, x2 = b1["x"] + b1["w"] / 2, b2["x"] + b2["w"] / 2
        focal = rel.get("focal", False)
        col = t["accent"] if focal else t["link"]
        mid = "aa" if focal else "al"
        parts.append(f'<path d="{elbow(x1, y1, x2, y2)}" fill="none" stroke="{col}" stroke-width="1.4" marker-end="url(#{mid})"/>')
        if rel.get("label"):
            parts.append(arrow_label(t, (x1 + x2) / 2, (y1 + y2) / 2, rel["label"].upper()))
    # Table cards
    for tid, b in table_boxes.items():
        x, y, w, h = b["x"], b["y"], b["w"], b["h"]
        tbl = b["tbl"]
        focal = tbl.get("focal", False)
        stroke = t["accent"] if focal else t["ink"]
        fill_head = t["accent_tint"] if focal else "rgba(45,49,66,0.06)"
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{t["card"]}" stroke="{stroke}" stroke-width="1.2"/>')
        parts.append(f'<path d="M{x},{y+36} L{x},{y+rx} Q{x},{y} {x+rx},{y} L{x+w-rx},{y} Q{x+w},{y} {x+w},{y+rx} L{x+w},{y+36} Z" fill="{fill_head}"/>')
        parts.append(f'<line x1="{x}" y1="{y+36}" x2="{x+w}" y2="{y+36}" stroke="{t["rule"]}" stroke-width="1"/>')
        parts.append(f'<text x="{x+12}" y="{y+23}" font-size="13" font-weight="600" font-family="{SANS}" fill="{t["ink"]}">{esc(tbl.get("name", tid))}</text>')
        tag = tbl.get("tag", "")
        if tag:
            tw = max(32, len(tag) * 7 + 8)
            parts.append(f'<rect x="{x+w-tw-10}" y="{y+12}" width="{tw}" height="14" rx="2" fill="none" stroke="{stroke}" stroke-opacity=".5" stroke-width=".8"/>')
            parts.append(f'<text x="{x+w-tw/2-10}" y="{y+22}" font-size="8" font-family="{MONO}" fill="{stroke}" text-anchor="middle">{esc(tag)}</text>')
        for c_idx, c in enumerate(tbl.get("columns", [])):
            cy = y + 44 + c_idx * row_h
            if c_idx > 0:
                parts.append(f'<line x1="{x+6}" y1="{cy}" x2="{x+w-6}" y2="{cy}" stroke="{t["rule"]}" stroke-width="0.5"/>')
            badge_x = x + 10
            if c.get("pk"):
                parts.append(f'<rect x="{badge_x}" y="{cy+4}" width="20" height="12" rx="2" fill="{t["accent"]}" fill-opacity=".15"/>')
                parts.append(f'<text x="{badge_x+10}" y="{cy+13}" font-size="7" font-weight="600" font-family="{MONO}" fill="{t["accent"]}" text-anchor="middle">PK</text>')
            elif c.get("fk"):
                parts.append(f'<rect x="{badge_x}" y="{cy+4}" width="20" height="12" rx="2" fill="{t["link"]}" fill-opacity=".15"/>')
                parts.append(f'<text x="{badge_x+10}" y="{cy+13}" font-size="7" font-weight="600" font-family="{MONO}" fill="{t["link"]}" text-anchor="middle">FK</text>')
            name_x = badge_x + (25 if (c.get("pk") or c.get("fk")) else 0)
            parts.append(f'<text x="{name_x}" y="{cy+15}" font-size="11" font-family="{MONO}" fill="{t["ink"]}">{esc(c["name"])}</text>')
            parts.append(f'<text x="{x+w-12}" y="{cy+15}" font-size="10" font-family="{MONO}" fill="{t["soft"]}" text-anchor="end">{esc(c.get("type",""))}</text>')
    if _notes:
        rail = []
        for nt in _notes:
            if nt.get("at") in table_boxes:
                b = table_boxes[nt["at"]]
                rail.append((b["x"] + b["w"], b["y"] + 18, nt["text"]))
        parts.append(render_noterail(t, rail, W - 186, 110))
    ly = H - 28
    parts.append(f'<line x1="30" y1="{ly-10}" x2="{W-30}" y2="{ly-10}" stroke="{t["rule"]}" stroke-width=".8"/>')
    parts.append(f'<text x="30" y="{ly+4}" font-size="11" font-family="{FONT}" fill="{t["muted"]}">pk = primary key, fk = foreign key, blue = relation, coral = focal</text>')
    parts.append("</svg>")
    return "\n".join(parts), W, H


def render_scatter(spec_path, xcol, ycol, title, subtitle, figure, xlabel, xunit, ylabel, yunit,
                    groupcol=None, yerrcol=None, facetcol=None, source="", corners="editorial",
                    chrome=True, width=760, facet_dir="row", theme=None, notes=None,
                    grid=True, markers=True, highlights=None):
    """Scatter: title and subtitle on the figure, nice ticks, groups, error bars, facets.
    chrome=False skips the heading. grid draws the tick rules. markers draws the dots.
    highlights (category, x, or group) are drawn larger in accent.
    facet_dir=row (side-by-side) or col (stacked, for social)."""
    import math
    t = theme or THEME
    rows = []
    with open(spec_path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        cols = r.fieldnames or []
        xc = xcol or cols[0]; yc = ycol or (cols[1] if len(cols) > 1 else cols[0])
        for row in r:
            try:
                d = {"x": float(row[xc]), "y": float(row[yc])}
                if groupcol and row.get(groupcol):
                    d["g"] = str(row[groupcol])
                if yerrcol and row.get(yerrcol):
                    d["ye"] = float(row[yerrcol])
                if facetcol and row.get(facetcol):
                    d["f"] = str(row[facetcol])
                rows.append(d)
            except ValueError:
                continue
    if not rows:
        raise SystemExit(f"{spec_path}: no numeric data in {xc}/{yc}")
    facets = sorted({d.get("f", "") for d in rows})
    multi = len(facets) > 1 or len(facets) == 1 and facetcol is not None
    groups = sorted({d.get("g", "") for d in rows if d.get("g")})
    _pal = series_palette(t)
    palette = {g: _pal[i % len(_pal)] for i, g in enumerate(groups)} if groups else {}
    # One scale for every facet, including the error bars, so panel B is comparable to panel A.
    xs = [d["x"] for d in rows]
    ylo = [d["y"] - d.get("ye", 0) for d in rows]
    yhi = [d["y"] + d.get("ye", 0) for d in rows]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ylo), max(yhi)
    if xmin == xmax:
        xmax = xmin + 1
    if ymin == ymax:
        ymax = ymin + 1
    padx, pady = (xmax - xmin) * 0.06, (ymax - ymin) * 0.08
    xmin -= padx
    xmax += padx
    ymin -= pady
    ymax += pady
    if min(xs) >= 0:
        xmin = max(0, xmin)
    if min(ylo) >= 0:
        ymin = max(0, ymin)
    xt = nice_ticks(xmin, xmax)
    yt = axis_ticks(ymin, ymax)

    def panel_svg(dset, panel_tag, px, py, pw, ph, show_y):
        sx = lambda v: px + (v - xt[0]) / (xt[-1] - xt[0]) * pw if len(xt) > 1 and xt[-1] != xt[0] else px + pw / 2
        sy = lambda v: (py + ph) - (v - yt[0]) / (yt[-1] - yt[0]) * ph if len(yt) > 1 and yt[-1] != yt[0] else py + ph / 2
        p = []
        # panel tag A/B
        if panel_tag:
            p.append(f'<text x="{px}" y="{py-10}" font-size="13" font-weight="600" font-family="{SANS}" fill="{t["ink"]}">{esc(panel_tag)}</text>')
        if grid:
            for v in xt:
                p.append(f'<line x1="{sx(v):.1f}" y1="{py}" x2="{sx(v):.1f}" y2="{py+ph}" stroke="{t["rule"]}" stroke-width="0.8"/>')
            for v in yt:
                p.append(f'<line x1="{px}" y1="{sy(v):.1f}" x2="{px+pw}" y2="{sy(v):.1f}" stroke="{t["rule"]}" stroke-width="0.8"/>')
        # decluttered spines: bottom + left only
        p.append(f'<line x1="{px}" y1="{py+ph}" x2="{px+pw}" y2="{py+ph}" stroke="{t["ink"]}" stroke-width="1.2"/>')
        p.append(f'<line x1="{px}" y1="{py}" x2="{px}" y2="{py+ph}" stroke="{t["ink"]}" stroke-width="1.2"/>')
        # error bars first, then points
        for d in dset[:400]:
            if "ye" in d:
                y1 = sy(d["y"] - d["ye"]); y2 = sy(d["y"] + d["ye"])
                col = palette.get(d.get("g", ""), t["muted"])
                p.append(f'<line x1="{sx(d["x"]):.1f}" y1="{y1:.1f}" x2="{sx(d["x"]):.1f}" y2="{y2:.1f}" stroke="{col}" stroke-width="1"/>')
                p.append(f'<line x1="{sx(d["x"])-4:.1f}" y1="{y1:.1f}" x2="{sx(d["x"])+4:.1f}" y2="{y1:.1f}" stroke="{col}"/>')
                p.append(f'<line x1="{sx(d["x"])-4:.1f}" y1="{y2:.1f}" x2="{sx(d["x"])+4:.1f}" y2="{y2:.1f}" stroke="{col}"/>')
        for d in dset[:400]:
            hit = _hit(highlights, d.get("g"), d["x"], fmt_tick(d["x"]))
            if not markers and not hit:
                continue
            col = t["accent"] if hit else palette.get(d.get("g", ""), t["muted"])
            rad = 6.4 if hit else 4.2
            p.append(f'<circle cx="{sx(d["x"]):.1f}" cy="{sy(d["y"]):.1f}" r="{rad}" fill="{col}" fill-opacity=".9" stroke="{t["card"]}" stroke-width="1"/>')
        for ni, pn in enumerate(notes or []):
            try:
                nx, ny = float(pn["x"]), float(pn["y"])
            except (KeyError, TypeError, ValueError):
                continue
            if len(xt) > 1 and len(yt) > 1 and xt[0] <= nx <= xt[-1] and yt[0] <= ny <= yt[-1] \
                    and ni not in drawn_notes:
                drawn_notes.add(ni)
                p.append(render_pincallout(t, sx(nx), sy(ny), pn.get("text", ""), top=py + 4))
        # ticks
        for v in xt:
            p.append(f'<text x="{sx(v):.1f}" y="{py+ph+18}" font-size="10" font-family="{MONO}" fill="{t["soft"]}" text-anchor="middle">{esc(fmt_tick(v))}</text>')
        if show_y:
            for v in yt:
                p.append(f'<text x="{px-8}" y="{sy(v)+3:.1f}" font-size="10" font-family="{MONO}" fill="{t["soft"]}" text-anchor="end">{esc(fmt_tick(v))}</text>')
        return "\n".join(p), len(dset)

    W = width
    faceted = bool(facetcol and len(facets) > 1)
    if chrome:
        head_bits, head_h = figure_heading(t, title, subtitle, x=36)
        if faceted:
            head_h += 18
    else:
        head_bits, head_h = [], 12
    if facet_dir == "col" and faceted:
        panel_h, gap = 250, 64
        fig_h = panel_h * len(facets) + gap * (len(facets) - 1)
        fig_w = W - 72
    else:
        fig_w, fig_h = W - 72, 360
    foot_h = 96 if groups else 70
    H = head_h + fig_h + foot_h + 30
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" viewBox="0 0 {W} {H}" width="{W}"><title>{esc(title)}</title>',
         f'<desc>{esc((subtitle + " " if subtitle else "") + (xlabel or "") + " vs " + (ylabel or ""))}</desc>',
         f'<rect width="{W}" height="{H}" fill="{t["card"]}"/>']
    s.extend(head_bits)
    ox, oy = 72, head_h
    drawn_notes = set()  # each pin drawn once (first panel whose domain contains it)
    if faceted and facet_dir == "col":
        for i, fv in enumerate(facets):
            dset = [d for d in rows if d.get("f") == fv]
            tag = chr(65 + i)
            label = tag if not fv or fv == tag else f"{tag} · {fv}"
            blk, _ = panel_svg(dset, label, ox, oy + i * (panel_h + gap), fig_w - 72, panel_h - 40, show_y=True)
            s.append(blk)
    elif faceted:
        gutter = 48
        pw = (fig_w - 72 - gutter * (len(facets) - 1)) / len(facets)
        for i, fv in enumerate(facets):
            dset = [d for d in rows if d.get("f") == fv]
            tag = chr(65 + i)
            label = tag if not fv or fv == tag else f"{tag} · {fv}"
            blk, _ = panel_svg(dset, label, ox + i * (pw + gutter), oy, pw, fig_h - 40, show_y=True)
            s.append(blk)
    else:
        blk, _ = panel_svg(rows, "", ox, oy, fig_w - 72, fig_h - 40, show_y=True)
        s.append(blk)
    # axis titles with units (clear of tick labels at +18)
    xlab = _with_unit(xlabel or _humanize(xc), xunit)
    ylab = _with_unit(ylabel or _humanize(yc), yunit)
    foot_top = oy + fig_h
    s.append(f'<text x="{ox + (fig_w-72)/2}" y="{foot_top+42}" font-size="12" font-weight="600" font-family="{SANS}" fill="{t["ink"]}" text-anchor="middle">{esc(xlab)}</text>')
    s.append(f'<text x="20" y="{oy + fig_h/2}" font-size="12" font-weight="600" font-family="{SANS}" fill="{t["ink"]}" text-anchor="middle" transform="rotate(-90 20,{oy + fig_h/2})">{esc(ylab)}</text>')
    # legend row below axis title
    if groups:
        lx, ly = ox, foot_top + 66
        for g in groups:
            s.append(f'<circle cx="{lx+6}" cy="{ly-4}" r="5" fill="{palette[g]}" stroke="{t["card"]}"/>')
            s.append(f'<text x="{lx+16}" y="{ly}" font-size="11" font-family="{SANS}" fill="{t["ink"]}">{esc(g)}</text>')
            lx += 16 + len(g) * 7 + 24
    # stats + source inside figure (no duplicated n)
    n = len(rows)
    note = f"n = {n}"
    if len(rows) > 2:
        try:
            mx = sum(d["x"] for d in rows) / n; my = sum(d["y"] for d in rows) / n
            num = sum((d["x"] - mx) * (d["y"] - my) for d in rows)
            den = (sum((d["x"] - mx) ** 2 for d in rows) * sum((d["y"] - my) ** 2 for d in rows)) ** 0.5
            if den:
                note += f" · Pearson r = {num/den:.2f}"
        except Exception:
            pass
    src = (source or "").strip()
    if src:
        import re as _re
        src = _re.sub(r"^\s*n\s*=\s*\d+\s*[·•\-–]\s*", "", src)  # caller already gets n
        note += f" · Source: {src}" if not src.lower().startswith("source") else f" · {src}"
    s.append(f'<text x="36" y="{H-12}" font-size="10.5" font-family="{MONO}" fill="{t["soft"]}">{esc(note)}</text>')
    s.append("</svg>")
    return "\n".join(s), W, H, n


def render_bar(spec_path, catcol, valcol, title, subtitle="", figure="Fig. 1",
               groupcol=None, orientation="v", sort="none", xlabel="", ylabel="",
               unit="", source="", corners="editorial", chrome=True, width=760, theme=None, notes=None,
               grid=True, markers=True, highlights=None):
    t = theme or THEME
    rows = []
    with open(spec_path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        cols = r.fieldnames or []
        cc = catcol or (cols[0] if cols else "")
        vc = valcol or (cols[1] if len(cols) > 1 else (cols[0] if cols else ""))
        for row in r:
            try:
                d = {"cat": str(row[cc]), "val": float(row[vc])}
                if groupcol and row.get(groupcol):
                    d["g"] = str(row[groupcol])
                rows.append(d)
            except (ValueError, KeyError, TypeError):
                continue
    if not rows:
        raise SystemExit(f"{spec_path}: no valid data in {cc}/{vc}")
    if sort == "asc":
        rows.sort(key=lambda d: d["val"])
    elif sort == "desc":
        rows.sort(key=lambda d: d["val"], reverse=True)
    vals = [d["val"] for d in rows]
    vmin, vmax = min(vals), max(vals)
    if vmin >= 0:
        vmin = 0
    if vmin == vmax:
        vmax = vmin + 1
    ticks = axis_ticks(vmin, vmax, n=5)
    span = (ticks[-1] - ticks[0]) or 1
    W = width
    head_bits, head_h = figure_heading(t, title, subtitle, x=36) if chrome else ([], 12)
    _bpal = series_palette(t)
    _bgroups = sorted({d.get("g", "") for d in rows if d.get("g")})
    _bmap = {g: _bpal[i % len(_bpal)] for i, g in enumerate(_bgroups)}
    horizontal = orientation == "h"
    cats, buckets = [], {}
    for d in rows:
        buckets.setdefault(d["cat"], []).append(d)
        if d["cat"] not in cats:
            cats.append(d["cat"])
    # one slot per category when a group column splits it; otherwise one bar per row
    slot_members = [buckets[c] for c in cats] if _bgroups else [[d] for d in rows]
    n = len(slot_members)
    rx = corner_rx(corners)
    if horizontal:
        label_w = min(200, max(88, max(len(s[0]["cat"]) for s in slot_members) * 6.6 + 18))
        ox = label_w
        oy = head_h + 8
        row_h = 32 if n > 8 else 40
        ph = max(160, n * row_h + 16)
        pw = W - ox - 72
        H = oy + ph + 72 + (26 if _bgroups else 0)
    else:
        ox, oy = 90, head_h
        pw, ph = W - ox - 48, 340
        slot_w = pw / max(1, n)
        wide = any(len(m[0]["cat"]) * 6.4 > slot_w * 0.9 for m in slot_members)
        H = head_h + ph + (128 if wide else 100) + (22 if _bgroups else 0)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" viewBox="0 0 {W} {H}" width="{W}"><title>{esc(title)}</title>',
             f'<desc>{esc(subtitle or (cc + " vs " + vc))}</desc>',
             f'<rect width="{W}" height="{H}" fill="{t["card"]}"/>']
    parts.extend(head_bits)

    def _sx(v):
        return ox + (v - ticks[0]) / span * pw

    def _sy(v):
        return (oy + ph) - (v - ticks[0]) / span * ph

    zero = 0 if ticks[0] <= 0 <= ticks[-1] else ticks[0]
    if horizontal:
        for v in ticks:
            x_pos = _sx(v)
            if grid:
                parts.append(f'<line x1="{x_pos:.1f}" y1="{oy}" x2="{x_pos:.1f}" y2="{oy+ph}" stroke="{t["rule"]}" stroke-width="0.8"/>')
            parts.append(f'<text x="{x_pos:.1f}" y="{oy+ph+16}" font-size="10" font-family="{MONO}" fill="{t["soft"]}" text-anchor="middle">{esc(fmt_tick(v))}</text>')
        parts.append(f'<line x1="{ox}" y1="{oy+ph}" x2="{ox+pw}" y2="{oy+ph}" stroke="{t["ink"]}" stroke-width="1.2"/>')
        parts.append(f'<line x1="{_sx(zero):.1f}" y1="{oy}" x2="{_sx(zero):.1f}" y2="{oy+ph}" stroke="{t["ink"]}" stroke-width="1.2"/>')
        band = ph / max(1, n)
        bar_h = min(22, band * 0.62)
        for i, members in enumerate(slot_members):
            cy = oy + (i + 0.5) * band
            gap = 3
            bh = min(bar_h, (band * 0.72 - gap * (len(members) - 1)) / len(members))
            top0 = cy - (bh * len(members) + gap * (len(members) - 1)) / 2
            parts.append(f'<text x="{ox-8}" y="{cy+4:.1f}" font-size="11" font-family="{SANS}" fill="{t["ink"]}" text-anchor="end">{esc(members[0]["cat"])}</text>')
            for j, d in enumerate(members):
                by = top0 + j * (bh + gap)
                x0, x1 = _sx(zero), _sx(d["val"])
                bx, bw = (x1, x0 - x1) if d["val"] < zero else (x0, x1 - x0)
                cap = "left" if d["val"] < zero else "right"
                hit = _hit(highlights, d["cat"], d.get("g"))
                col = t["accent"] if hit else _bmap.get(d.get("g", ""), t["link"])
                grow = 2 if hit else 0
                shape = bar_path(bx, by - grow / 2, bw, bh + grow, rx, cap)
                if shape:
                    edge = f' stroke="{t["ink"]}" stroke-width="1.2"' if hit else ""
                    parts.append(f'{shape} fill="{col}" fill-opacity="{"0.95" if hit else "0.85"}"{edge}/>')
                if markers:
                    val_str = fmt_tick(d["val"]) + (f" {unit}" if unit else "")
                    outside = (bx - 6) if d["val"] < zero else (bx + bw + 6)
                    if d["val"] >= zero and outside > ox + pw - 28:
                        parts.append(f'<text x="{bx+bw-4:.1f}" y="{by+bh/2+3:.1f}" font-size="10" font-family="{MONO}" fill="{t["card"]}" text-anchor="end">{esc(val_str)}</text>')
                    else:
                        anchor = "end" if d["val"] < zero else "start"
                        parts.append(f'<text x="{outside:.1f}" y="{by+bh/2+3:.1f}" font-size="10" font-family="{MONO}" fill="{t["ink"]}" text-anchor="{anchor}">{esc(val_str)}</text>')
        legend_y = oy + ph + 28
    else:
        for v in ticks:
            y_pos = _sy(v)
            if grid:
                parts.append(f'<line x1="{ox}" y1="{y_pos:.1f}" x2="{ox+pw}" y2="{y_pos:.1f}" stroke="{t["rule"]}" stroke-width="0.8"/>')
            parts.append(f'<text x="{ox-8}" y="{y_pos+3:.1f}" font-size="10" font-family="{MONO}" fill="{t["soft"]}" text-anchor="end">{esc(fmt_tick(v))}</text>')
        base_y = _sy(zero)
        parts.append(f'<line x1="{ox}" y1="{base_y:.1f}" x2="{ox+pw}" y2="{base_y:.1f}" stroke="{t["ink"]}" stroke-width="1.2"/>')
        parts.append(f'<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{oy+ph}" stroke="{t["ink"]}" stroke-width="1.2"/>')
        for i, members in enumerate(slot_members):
            gap = 4
            inner = slot_w * 0.7
            bw = min(48, (inner - gap * (len(members) - 1)) / max(1, len(members)))
            origin = ox + i * slot_w + (slot_w - (bw * len(members) + gap * (len(members) - 1))) / 2
            for j, d in enumerate(members):
                bx = origin + j * (bw + gap)
                y_val = _sy(d["val"])
                y0 = base_y
                by, bh = (y_val, y0 - y_val) if d["val"] >= zero else (y0, y_val - y0)
                by = min(max(by, oy), oy + ph)
                bh = max(0.0, min(bh, oy + ph - by))
                cap = "bottom" if d["val"] < zero else "top"
                hit = _hit(highlights, d["cat"], d.get("g"))
                col = t["accent"] if hit else _bmap.get(d.get("g", ""), t["link"])
                grow = 3 if hit else 0
                shape = bar_path(bx - grow / 2, by, bw + grow, bh, rx, cap)
                if shape:
                    edge = f' stroke="{t["ink"]}" stroke-width="1.2"' if hit else ""
                    parts.append(f'{shape} fill="{col}" fill-opacity="{"0.95" if hit else "0.85"}"{edge}/>')
                if markers:
                    val_str = fmt_tick(d["val"]) + (f" {unit}" if unit else "")
                    tip = by if d["val"] >= zero else by + bh
                    if d["val"] >= zero and tip < oy + 18:
                        parts.append(f'<text x="{bx+bw/2:.1f}" y="{tip+13:.1f}" font-size="10" font-family="{MONO}" fill="{t["card"]}" text-anchor="middle">{esc(val_str)}</text>')
                    else:
                        ly = tip - 6 if d["val"] >= zero else tip + 14
                        parts.append(f'<text x="{bx+bw/2:.1f}" y="{ly:.1f}" font-size="10" font-family="{MONO}" fill="{t["ink"]}" text-anchor="middle">{esc(val_str)}</text>')
            cx = ox + (i + 0.5) * slot_w
            ly = oy + ph + 18
            if wide:
                parts.append(f'<text x="{cx:.1f}" y="{ly:.1f}" font-size="10.5" font-family="{SANS}" fill="{t["ink"]}" text-anchor="end" transform="rotate(-40 {cx:.1f} {ly:.1f})">{esc(members[0]["cat"])}</text>')
            else:
                parts.append(f'<text x="{cx:.1f}" y="{ly:.1f}" font-size="10.5" font-family="{SANS}" fill="{t["ink"]}" text-anchor="middle">{esc(members[0]["cat"])}</text>')
        legend_y = oy + ph + (56 if wide else 36)
    for nt in (notes or [])[:2]:
        hit = next((d for d in rows if d["cat"] == nt.get("at")), None)
        if hit is None:
            continue
        if horizontal:
            idx = next(i for i, m in enumerate(slot_members) if m[0]["cat"] == hit["cat"])
            cy = oy + (idx + 0.5) * (ph / max(1, n))
            parts.append(render_pincallout(t, _sx(hit["val"]), cy, nt.get("text", ""), above=False, top=oy + 4))
        else:
            idx = next(i for i, m in enumerate(slot_members) if any(d["cat"] == hit["cat"] for d in m))
            cx = ox + (idx + 0.5) * (pw / max(1, n))
            parts.append(render_pincallout(t, cx, _sy(hit["val"]), nt.get("text", ""), top=oy + 4))
    if _bgroups:
        lx = ox
        for g in _bgroups:
            parts.append(f'<rect x="{lx}" y="{legend_y}" width="12" height="12" rx="2" fill="{_bmap[g]}"/>')
            parts.append(f'<text x="{lx+18}" y="{legend_y+10}" font-size="11" font-family="{SANS}" fill="{t["ink"]}">{esc(g)}</text>')
            lx += 18 + len(g) * 7 + 24
    _fx = (legend_y - (oy + ph) + 28) if horizontal else (legend_y - base_y + 22)
    if xlabel or catcol:
        xlab = xlabel or ("" if horizontal else _humanize(catcol))
        if horizontal and not xlabel:
            xlab = ""
        if xlab:
            parts.append(f'<text x="{ox+pw/2}" y="{oy+ph+_fx}" font-size="12" font-weight="600" font-family="{SANS}" fill="{t["ink"]}" text-anchor="middle">{esc(xlab)}</text>')
    ylbl = _with_unit(ylabel or (_humanize(valcol) if horizontal else _humanize(valcol)), unit)
    if horizontal:
        if ylabel or valcol:
            parts.append(f'<text x="{ox+pw/2}" y="{H-16}" font-size="12" font-weight="600" font-family="{SANS}" fill="{t["ink"]}" text-anchor="middle">{esc(ylbl)}</text>')
    elif ylabel or valcol:
        parts.append(f'<text x="22" y="{oy+ph/2}" font-size="12" font-weight="600" font-family="{SANS}" fill="{t["ink"]}" text-anchor="middle" transform="rotate(-90 22,{oy+ph/2})">{esc(ylbl)}</text>')
    src_note = f"n = {len(rows)}" + (f" · Source: {source}" if source else "")
    parts.append(f'<text x="36" y="{H-14}" font-size="10.5" font-family="{MONO}" fill="{t["soft"]}">{esc(src_note)}</text>')
    parts.append("</svg>")
    return "\n".join(parts), W, H, len(rows)


def render_line(spec_path, xcol, ycol, title, subtitle="", figure="Fig. 1",
                groupcol=None, xlabel="", xunit="", ylabel="", yunit="",
                source="", corners="editorial", chrome=True, width=760, theme=None, notes=None,
                grid=True, markers=True, highlights=None):
    t = theme or THEME
    rows = []
    with open(spec_path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        cols = r.fieldnames or []
        xc = xcol or (cols[0] if cols else "")
        yc = ycol or (cols[1] if len(cols) > 1 else (cols[0] if cols else ""))
        for row in r:
            try:
                x_val = row[xc]
                try:
                    num_x = float(x_val)
                except ValueError:
                    num_x = None
                y_val = float(row[yc])
                d = {"x_str": x_val, "x_num": num_x, "y": y_val}
                if groupcol and row.get(groupcol):
                    d["g"] = str(row[groupcol])
                rows.append(d)
            except (ValueError, KeyError, TypeError):
                continue
    if not rows:
        raise SystemExit(f"{spec_path}: no valid data in {xc}/{yc}")
    groups = sorted({d.get("g", "default") for d in rows})
    _pal = series_palette(t)
    palette = {g: _pal[i % len(_pal)] for i, g in enumerate(groups)}
    ys = [d["y"] for d in rows]
    ymin, ymax = min(ys), max(ys)
    if min(ys) >= 0:
        ymin = 0
    if ymin == ymax:
        ymax = ymin + 1
    yt = nice_ticks(ymin, ymax, n=5)
    W = width
    head_bits, head_h = figure_heading(t, title, subtitle, x=36) if chrome else ([], 12)
    H = head_h + 360 + (80 if len(groups) > 1 else 60)
    ox, oy = 80, head_h
    pw, ph = W - ox - 40, 320
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" viewBox="0 0 {W} {H}" width="{W}"><title>{esc(title)}</title>',
             f'<desc>{esc(subtitle or (xc + " vs " + yc))}</desc>',
             f'<rect width="{W}" height="{H}" fill="{t["card"]}"/>']
    parts.extend(head_bits)
    sy = lambda v: (oy + ph) - (v - yt[0]) / (yt[-1] - yt[0]) * ph if yt[-1] != yt[0] else oy + ph / 2
    for v in yt:
        y_pos = sy(v)
        if grid:
            parts.append(f'<line x1="{ox}" y1="{y_pos:.1f}" x2="{ox+pw}" y2="{y_pos:.1f}" stroke="{t["rule"]}" stroke-width="0.8"/>')
        parts.append(f'<text x="{ox-10}" y="{y_pos+4:.1f}" font-size="10" font-family="{MONO}" fill="{t["soft"]}" text-anchor="end">{esc(fmt_tick(v))}</text>')
    is_numeric_x = all(d["x_num"] is not None for d in rows)
    if is_numeric_x:
        x_nums = [d["x_num"] for d in rows]
        xmin, xmax = min(x_nums), max(x_nums)
        if xmin == xmax: xmax = xmin + 1
        xt = nice_ticks(xmin, xmax, n=5)
        sx = lambda v: ox + (v - xt[0]) / (xt[-1] - xt[0]) * pw if xt[-1] != xt[0] else ox + pw / 2
        for v in xt:
            if grid:
                parts.append(f'<line x1="{sx(v):.1f}" y1="{oy}" x2="{sx(v):.1f}" y2="{oy+ph}" stroke="{t["rule"]}" stroke-width="0.8"/>')
            parts.append(f'<text x="{sx(v):.1f}" y="{oy+ph+18}" font-size="10" font-family="{MONO}" fill="{t["soft"]}" text-anchor="middle">{esc(fmt_tick(v))}</text>')
    else:
        x_labels = []
        for d in rows:
            if d["x_str"] not in x_labels:
                x_labels.append(d["x_str"])
        n_xl = len(x_labels)
        sx_map = {lbl: ox + (i / max(1, n_xl - 1)) * pw for i, lbl in enumerate(x_labels)}
        sx = lambda lbl: sx_map[lbl]
        for lbl in x_labels:
            xp = sx(lbl)
            if grid:
                parts.append(f'<line x1="{xp:.1f}" y1="{oy}" x2="{xp:.1f}" y2="{oy+ph}" stroke="{t["rule"]}" stroke-width="0.8"/>')
            parts.append(f'<text x="{xp:.1f}" y="{oy+ph+18}" font-size="10" font-family="{MONO}" fill="{t["soft"]}" text-anchor="middle">{esc(lbl)}</text>')
    parts.append(f'<line x1="{ox}" y1="{oy+ph}" x2="{ox+pw}" y2="{oy+ph}" stroke="{t["ink"]}" stroke-width="1.2"/>')
    parts.append(f'<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{oy+ph}" stroke="{t["ink"]}" stroke-width="1.2"/>')
    for g in groups:
        g_rows = [d for d in rows if d.get("g", "default") == g]
        if not g_rows:
            continue
        pts = []
        for d in g_rows:
            xp = sx(d["x_num"]) if is_numeric_x else sx(d["x_str"])
            yp = sy(d["y"])
            pts.append((xp, yp))
        col = palette[g]
        if len(groups) == 1:
            poly_pts = f"{pts[0][0]:.1f},{oy+ph} " + " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in pts) + f" {pts[-1][0]:.1f},{oy+ph}"
            parts.append(f'<polygon points="{poly_pts}" fill="{col}" fill-opacity="0.08"/>')
        path_d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f} " + " ".join(f"L{p[0]:.1f},{p[1]:.1f}" for p in pts[1:])
        parts.append(f'<path d="{path_d}" fill="none" stroke="{col}" stroke-width="2.2" stroke-linecap="round"/>')
        for i, (xp, yp) in enumerate(pts):
            d = g_rows[i]
            hit = _hit(highlights, d["x_str"], d.get("g"), d["x_num"])
            if not markers and not hit:
                continue
            mcol = t["accent"] if hit else col
            rad = 5.6 if hit else 3.5
            parts.append(f'<circle cx="{xp:.1f}" cy="{yp:.1f}" r="{rad}" fill="{mcol}" stroke="{t["card"]}" stroke-width="1.2"/>')
    for nt in (notes or [])[:2]:
        ax, best, bd = nt.get("at"), None, None
        try:
            av = float(ax)
            for d in rows:
                if d["x_num"] is None:
                    continue
                delta = abs(d["x_num"] - av)
                if bd is None or delta < bd:
                    best, bd = d, delta
        except (TypeError, ValueError):
            best = next((d for d in rows if d["x_str"] == ax), None)
        if best is None:
            continue
        xp = sx(best["x_num"]) if is_numeric_x and best["x_num"] is not None else sx(best["x_str"])
        parts.append(render_pincallout(t, xp, sy(best["y"]), nt.get("text", ""), top=oy + 4))
    xlab = _with_unit(xlabel or _humanize(xc), xunit)
    ylab = _with_unit(ylabel or _humanize(yc), yunit)
    parts.append(f'<text x="{ox+pw/2}" y="{oy+ph+40}" font-size="12" font-weight="600" font-family="{SANS}" fill="{t["ink"]}" text-anchor="middle">{esc(xlab)}</text>')
    if len(groups) > 1 and groups != ["default"]:
        lx, ly = ox, oy + ph + 66
        for g in groups:
            parts.append(f'<line x1="{lx}" y1="{ly}" x2="{lx+16}" y2="{ly}" stroke="{palette[g]}" stroke-width="2.5"/>')
            parts.append(f'<circle cx="{lx+8}" cy="{ly}" r="3.5" fill="{palette[g]}" stroke="{t["card"]}" stroke-width="1"/>')
            parts.append(f'<text x="{lx+24}" y="{ly+4}" font-size="11" font-family="{SANS}" fill="{t["ink"]}">{esc(g)}</text>')
            lx += 24 + len(g) * 7 + 24
    parts.append(f'<text x="24" y="{oy+ph/2}" font-size="12" font-weight="600" font-family="{SANS}" fill="{t["ink"]}" text-anchor="middle" transform="rotate(-90 24,{oy+ph/2})">{esc(ylab)}</text>')
    src_note = f"n = {len(rows)}" + (f" · Source: {source}" if source else "")
    parts.append(f'<text x="36" y="{H-14}" font-size="10.5" font-family="{MONO}" fill="{t["soft"]}">{esc(src_note)}</text>')
    parts.append("</svg>")
    return "\n".join(parts), W, H, len(rows)


# Coastline packed as zlib+base64 of "lon_tenth,lat_tenth ..." rings separated by ";".
# Natural Earth 110m land, simplified. Drawn under the points. Not a tiled basemap.
LAND_B64 = """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"""


def _land_rings():
    if getattr(_land_rings, "cache", None) is None:
        rings = []
        if LAND_B64:
            import base64, zlib
            raw = zlib.decompress(base64.b64decode(LAND_B64)).decode()
            for part in raw.split(";"):
                pts = []
                for pair in part.split():
                    a, b = pair.split(",")
                    pts.append((int(a) / 10.0, int(b) / 10.0))
                if len(pts) >= 3:
                    rings.append(pts)
        _land_rings.cache = rings
    return _land_rings.cache


def _clip_poly(ring, minx, miny, maxx, maxy):
    """Sutherland–Hodgman clip of a lon/lat ring to a box."""
    def edge(poly, inside, cross):
        if not poly:
            return []
        out, prev = [], poly[-1]
        pin = inside(prev)
        for cur in poly:
            cin = inside(cur)
            if cin:
                if not pin:
                    out.append(cross(prev, cur))
                out.append(cur)
            elif pin:
                out.append(cross(prev, cur))
            prev, pin = cur, cin
        return out

    def lerp(a, b, t):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    def xclip(poly, x, keep_left):
        def inside(p):
            return p[0] <= x if keep_left else p[0] >= x
        def cross(a, b):
            dx = b[0] - a[0]
            t = 0.0 if dx == 0 else (x - a[0]) / dx
            return lerp(a, b, max(0.0, min(1.0, t)))
        return edge(poly, inside, cross)

    def yclip(poly, y, keep_low):
        def inside(p):
            return p[1] <= y if keep_low else p[1] >= y
        def cross(a, b):
            dy = b[1] - a[1]
            t = 0.0 if dy == 0 else (y - a[1]) / dy
            return lerp(a, b, max(0.0, min(1.0, t)))
        return edge(poly, inside, cross)

    ring = xclip(ring, maxx, True)
    ring = xclip(ring, minx, False)
    ring = yclip(ring, maxy, True)
    ring = yclip(ring, miny, False)
    return ring


def _map_colors(t):
    paper = t.get("paper") or ""
    dark = False
    if paper.startswith("#") and len(paper) >= 7:
        r, g, b = int(paper[1:3], 16), int(paper[3:5], 16), int(paper[5:7], 16)
        dark = 0.3 * r + 0.59 * g + 0.11 * b < 140
    if dark:
        return "#1c2838", "#3a4358", "#8b95a8"
    return "#d5e3ec", "#f4f0e8", "#8d97a8"


def _merc(lon, lat):
    import math
    lat = max(-85.0, min(85.0, float(lat)))
    x = math.radians(float(lon))
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def _load_geo(path, latcol, loncol, labelcol, valcol):
    """CSV points, or GeoJSON points / polygon rings. Returns points, rings, value label."""
    points, rings = [], []
    if path.lower().endswith(".csv"):
        with open(path, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            cols = r.fieldnames or []
            def pick(pref, fallbacks):
                if pref and pref in cols:
                    return pref
                for c in cols:
                    if c.lower() in fallbacks:
                        return c
                return None
            lc = pick(latcol, ("lat", "latitude", "y"))
            nc = pick(loncol, ("lon", "lng", "long", "longitude", "x"))
            if not lc or not nc:
                raise SystemExit(f"{path}: need lat/lon columns, got {cols}")
            lb = pick(labelcol, ("name", "city", "label"))
            vc = pick(valcol, ("value", "val", "pop", "weight"))
            for row in r:
                try:
                    item = {"lat": float(row[lc]), "lon": float(row[nc]),
                            "label": (row.get(lb) or "") if lb else "",
                            "val": float(row[vc]) if vc and row.get(vc) not in (None, "") else None}
                except (TypeError, ValueError, KeyError):
                    continue
                if not (-90 <= item["lat"] <= 90 and -180 <= item["lon"] <= 180):
                    continue
                points.append(item)
        return points, rings
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    feats = data.get("features", []) if isinstance(data, dict) else []
    for ft in feats:
        g = ft.get("geometry") or {}
        props = ft.get("properties") or {}
        label = str(props.get(labelcol) or props.get("name") or props.get("city") or "")
        raw = props.get(valcol) if valcol else props.get("value")
        try:
            val = float(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            val = None
        gt = g.get("type")
        coords = g.get("coordinates") or []
        if gt == "Point" and len(coords) >= 2:
            lon, lat = coords[0], coords[1]
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                points.append({"lat": lat, "lon": lon, "label": label, "val": val})
        elif gt == "Polygon":
            if coords:
                rings.append(coords[0])
        elif gt == "MultiPolygon":
            for poly in coords:
                if poly:
                    rings.append(poly[0])
    return points, rings


def render_geo(spec_path, latcol=None, loncol=None, labelcol=None, valcol=None,
               title="Map", subtitle="", figure="Fig. 1", source="", theme=None, width=760, chrome=True,
               grid=True, markers=True, highlights=None):
    """Point map on a built-in coastline. Web Mercator. GeoJSON polygons are drawn on top.
    Stdlib only. A figure, not a tiled GIS."""
    import math
    t = theme or THEME
    points, rings = _load_geo(spec_path, latcol, loncol, labelcol, valcol)
    samples = [(p["lon"], p["lat"]) for p in points]
    for ring in rings:
        for c in ring:
            if len(c) >= 2:
                samples.append((c[0], c[1]))
    if len(samples) < 1:
        raise SystemExit(f"{spec_path}: no coordinates")
    lons = [s[0] for s in samples]
    lats = [s[1] for s in samples]
    minlon, maxlon = min(lons), max(lons)
    minlat, maxlat = min(lats), max(lats)
    if maxlon - minlon < 0.4:
        mid = (minlon + maxlon) / 2
        minlon, maxlon = mid - 0.3, mid + 0.3
    if maxlat - minlat < 0.4:
        mid = (minlat + maxlat) / 2
        minlat, maxlat = mid - 0.25, mid + 0.25
    pad_x = (maxlon - minlon) * 0.08
    pad_y = (maxlat - minlat) * 0.08
    minlon -= pad_x
    maxlon += pad_x
    minlat -= pad_y
    maxlat += pad_y
    corners = [_merc(minlon, minlat), _merc(maxlon, minlat), _merc(minlon, maxlat), _merc(maxlon, maxlat)]
    minx = min(c[0] for c in corners)
    maxx = max(c[0] for c in corners)
    miny = min(c[1] for c in corners)
    maxy = max(c[1] for c in corners)
    W = width
    head_bits, head_h = figure_heading(t, title, subtitle, x=36) if chrome else ([], 12)
    ox, oy = 48, head_h
    pw, ph = W - ox - 36, 420
    H = oy + ph + 56
    sx = (maxx - minx) or 1
    sy = (maxy - miny) or 1
    # fit, preserving mercator aspect inside the panel
    aspect = sx / sy
    panel_aspect = pw / ph
    if aspect > panel_aspect:
        used_w, used_h = pw, pw / aspect
    else:
        used_h, used_w = ph, ph * aspect
    x0 = ox + (pw - used_w) / 2
    y0 = oy + (ph - used_h) / 2

    def proj(lon, lat):
        mx, my = _merc(lon, lat)
        px = x0 + (mx - minx) / sx * used_w
        py = y0 + (maxy - my) / sy * used_h
        return px, py

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" viewBox="0 0 {W} {H}" width="{W}"><title>{esc(title)}</title>',
             f'<desc>{esc(subtitle or "Locations")}</desc>',
             f'<rect width="{W}" height="{H}" fill="{t["card"]}"/>']
    parts.extend(head_bits)
    water, land, coast = _map_colors(t)
    parts.append(f'<rect x="{ox}" y="{oy}" width="{pw}" height="{ph}" fill="{water}" stroke="{t["rule"]}"/>')
    parts.append(f'<clipPath id="mapframe"><rect x="{x0:.1f}" y="{y0:.1f}" width="{used_w:.1f}" height="{used_h:.1f}"/></clipPath>')
    parts.append('<g clip-path="url(#mapframe)">')
    for ring in _land_rings():
        lons_r = [p[0] for p in ring]
        lats_r = [p[1] for p in ring]
        if max(lons_r) < minlon or min(lons_r) > maxlon or max(lats_r) < minlat or min(lats_r) > maxlat:
            continue
        clipped = _clip_poly(ring, minlon, minlat, maxlon, maxlat)
        if len(clipped) < 3:
            continue
        seq = []
        for lon, lat in clipped:
            px, py = proj(lon, lat)
            seq.append(f"{px:.1f},{py:.1f}")
        parts.append(f'<polygon points="{" ".join(seq)}" fill="{land}" stroke="{coast}" stroke-width="0.7" stroke-linejoin="round"/>')
    # graticule on nice degree steps
    span = max(maxlon - minlon, maxlat - minlat)
    step = 1
    for cand in (1, 2, 5, 10, 15, 30, 45):
        if span / cand <= 6:
            step = cand
            break
    def nice_deg(lo, hi):
        import math as _m
        a = _m.ceil(lo / step) * step
        v = a
        while v < hi - 1e-9:
            yield v
            v += step
    labels = []
    for lon in nice_deg(minlon, maxlon):
        x, _ = proj(lon, (minlat + maxlat) / 2)
        if grid:
            parts.append(f'<line x1="{x:.1f}" y1="{y0:.1f}" x2="{x:.1f}" y2="{y0+used_h:.1f}" stroke="{coast}" stroke-opacity="0.55" stroke-width="0.7"/>')
        labels.append(f'<text x="{x:.1f}" y="{y0+used_h+14:.1f}" font-size="9" font-family="{MONO}" fill="{t["soft"]}" text-anchor="middle">{lon:.0f}°</text>')
    for lat in nice_deg(minlat, maxlat):
        _, y = proj((minlon + maxlon) / 2, lat)
        if grid:
            parts.append(f'<line x1="{x0:.1f}" y1="{y:.1f}" x2="{x0+used_w:.1f}" y2="{y:.1f}" stroke="{coast}" stroke-opacity="0.55" stroke-width="0.7"/>')
        labels.append(f'<text x="{x0-6:.1f}" y="{y+3:.1f}" font-size="9" font-family="{MONO}" fill="{t["soft"]}" text-anchor="end">{lat:.0f}°</text>')
    vals = [p["val"] for p in points if p["val"] is not None]
    vmin, vmax = (min(vals), max(vals)) if vals else (0, 1)
    if vmin == vmax:
        vmax = vmin + 1
    for ring in rings:
        seq = []
        for c in ring:
            if len(c) < 2:
                continue
            px, py = proj(c[0], c[1])
            seq.append(f"{px:.1f},{py:.1f}")
        if len(seq) >= 3:
            parts.append(f'<polygon points="{" ".join(seq)}" fill="{t["accent_tint"]}" stroke="{t["ink"]}" stroke-width="1"/>')
    parts.append("</g>")
    parts.extend(labels)
    show_labels = len(points) <= 16
    for p in points:
        hit = _hit(highlights, p["label"], p["lat"], p["lon"])
        if not markers and not hit:
            continue
        px, py = proj(p["lon"], p["lat"])
        if p["val"] is None:
            r = 4.5
            col = t["accent"]
        else:
            u = (p["val"] - vmin) / (vmax - vmin)
            r = 4 + 10 * u
            col = t["link"] if u < 0.66 else t["accent"]
        if hit:
            col = t["accent"]
            r += 3
        parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{r:.1f}" fill="{col}" fill-opacity="0.9" stroke="{t["card"]}" stroke-width="{"1.6" if hit else "1"}"/>')
        if (show_labels or hit) and p["label"]:
            parts.append(f'<text x="{px+r+4:.1f}" y="{py-r:.1f}" font-size="11" font-family="{SANS}" fill="{t["ink"]}">{esc(p["label"])}</text>')
    # scale bar from mercator metres at mid latitude
    midlat = (minlat + maxlat) / 2
    m_per_rad = 6378137 * math.cos(math.radians(midlat))
    m_per_px = m_per_rad / (used_w / sx)
    target = used_w * 0.22 * m_per_px
    nice_m = 1
    for cand in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000):
        if cand * 1000 <= target:
            nice_m = cand
    bar_px = (nice_m * 1000) / m_per_px if m_per_px else 40
    bx, by = x0 + 12, y0 + used_h - 18
    parts.append(f'<rect x="{bx-4:.1f}" y="{by-18:.1f}" width="{bar_px+12:.1f}" height="26" fill="{water}" fill-opacity="0.92"/>')
    parts.append(f'<line x1="{bx:.1f}" y1="{by:.1f}" x2="{bx+bar_px:.1f}" y2="{by:.1f}" stroke="{t["ink"]}" stroke-width="2"/>')
    parts.append(f'<line x1="{bx:.1f}" y1="{by-4:.1f}" x2="{bx:.1f}" y2="{by+4:.1f}" stroke="{t["ink"]}" stroke-width="1.2"/>')
    parts.append(f'<line x1="{bx+bar_px:.1f}" y1="{by-4:.1f}" x2="{bx+bar_px:.1f}" y2="{by+4:.1f}" stroke="{t["ink"]}" stroke-width="1.2"/>')
    unit = f"{nice_m} km" if nice_m < 1000 else f"{nice_m/1000:g}k km"
    parts.append(f'<text x="{bx:.1f}" y="{by-8:.1f}" font-size="10" font-family="{MONO}" fill="{t["ink"]}">{esc(unit)}</text>')
    # north
    nx, ny = x0 + used_w - 18, y0 + 22
    parts.append(f'<line x1="{nx:.1f}" y1="{ny+16:.1f}" x2="{nx:.1f}" y2="{ny-10:.1f}" stroke="{t["ink"]}" stroke-width="1.2"/>')
    parts.append(f'<polygon points="{nx:.1f},{ny-16:.1f} {nx-4:.1f},{ny-6:.1f} {nx+4:.1f},{ny-6:.1f}" fill="{t["ink"]}"/>')
    parts.append(f'<text x="{nx+8:.1f}" y="{ny-8:.1f}" font-size="10" font-family="{MONO}" fill="{t["ink"]}">N</text>')
    note = f"n = {len(points)}"
    if rings:
        note += f" · {len(rings)} polygons"
    if source:
        note += f" · Source: {source}"
    note += " · Web Mercator"
    parts.append(f'<text x="36" y="{H-14}" font-size="10.5" font-family="{MONO}" fill="{t["soft"]}">{esc(note)}</text>')
    parts.append("</svg>")
    return "\n".join(parts), W, H, len(points)


def write_out(svg, kind, title, sub, eyebrow, out, caption="", cap_title="", source="", corners="editorial", theme=None):
    t = theme or THEME
    base, _ext = os.path.splitext(out)
    h = HTML_SHELL.format(paper=t["paper"], ink=t["ink"], rule=t["rule"], card=t["card"],
                          font=FONT, title=esc(title), svg=svg)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(h)
    svg_path = base + ".svg"
    # extract inner svg for embed use
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)
    return out, svg_path


LAYOUTS = {
    # name -> (width, facet_dir, chrome): doc presets for export
    "figure": {"width": 760, "facet_dir": "row", "chrome": True},
    "wide": {"width": 1120, "facet_dir": "row", "chrome": True},
    "slide": {"width": 1280, "facet_dir": "row", "chrome": True},
    "social": {"width": 1080, "facet_dir": "col", "chrome": True},
}


def save_receipt(out, payload):
    base, _ = os.path.splitext(out)
    with open(base + ".graph.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _browser():
    import shutil
    for name in ("msedge", "microsoft-edge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _raster_svg(svg, dest, kind, width_hint):
    """Write a PNG or PDF of the SVG. Cairo if it imports, otherwise Edge or Chrome headless."""
    import re, shutil, subprocess, tempfile
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    w = max(1, int(round(float(m.group(1))))) if m else int(width_hint)
    h = max(1, int(round(float(m.group(2))))) if m else int(width_hint * 0.75)
    try:
        import cairosvg
        kw = {"write_to": dest, "output_width": width_hint} if kind == "png" else {"write_to": dest}
        getattr(cairosvg, f"svg2{kind}")(bytestring=svg.encode("utf-8"), **kw)
        return "cairosvg"
    except (ImportError, OSError):
        pass
    browser = _browser()
    if not browser:
        return None
    folder = tempfile.mkdtemp(prefix="graph-raster-")
    page = os.path.join(folder, "fig.html")
    html = ("<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
            f"html,body{{margin:0;padding:0;width:{w}px;height:{h}px;overflow:hidden;background:#fff}}"
            "svg{display:block;width:100%;height:100%}</style></head><body>"
            + svg + "</body></html>")
    with open(page, "w", encoding="utf-8") as f:
        f.write(html)
    url = "file:///" + os.path.abspath(page).replace("\\", "/")
    profile = os.path.join(folder, "profile")
    dest_abs = os.path.abspath(dest)
    if kind == "pdf":
        cmd = [browser, "--headless=new", "--disable-gpu", f"--user-data-dir={profile}",
               "--no-pdf-header-footer", f"--print-to-pdf={dest_abs}", url]
    else:
        cmd = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
               "--force-device-scale-factor=2", f"--user-data-dir={profile}",
               f"--window-size={w},{h}", f"--screenshot={dest_abs}", url]
    try:
        subprocess.run(cmd, check=True, timeout=90, capture_output=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        shutil.rmtree(folder, ignore_errors=True)
        return None
    shutil.rmtree(folder, ignore_errors=True)
    if os.path.isfile(dest_abs) and os.path.getsize(dest_abs) > 400:
        return "browser"
    return None


def do_export(args):
    base = args.target
    for ext in (".graph.json", ".html", ".svg"):
        if base.endswith(ext):
            base = base[: -len(ext)]
    rcpt = base + ".graph.json"
    if not os.path.exists(rcpt):
        sys.exit(f"no receipt {rcpt} — re-render with: py graph.py scatter ... -o {base}.html")
    with open(rcpt, encoding="utf-8") as f:
        r = json.load(f)
    cmd, lay = r.get("cmd", "scatter"), LAYOUTS[args.layout]
    theme = get_theme(args.theme or r.get("theme") or "editorial", args.theme_file)
    note = ""
    if cmd == "scatter":
        svg, _, _, n = render_scatter(r["csv"], r.get("x"), r.get("y"), r.get("title", "Scatter"),
                                      r.get("subtitle", ""), r.get("figure", "Fig. 1"),
                                      r.get("xlabel", ""), r.get("xunit", ""), r.get("ylabel", ""),
                                      r.get("yunit", ""), r.get("group"), r.get("yerr"), r.get("facet"),
                                      r.get("source", ""), r.get("corners", "editorial"),
                                      chrome=lay["chrome"], width=lay["width"], facet_dir=lay["facet_dir"],
                                      theme=theme, grid=r.get("grid", True), markers=r.get("markers", True),
                                      highlights=r.get("highlights") or None)
        unit, dest = "points", args.o or f"{base}-{args.layout}.{args.to}"
    elif cmd == "bar":
        svg, _, _, n = render_bar(r["csv"], r.get("cat"), r.get("val"), r.get("title", "Bar Chart"),
                                  r.get("subtitle", ""), r.get("figure", "Fig. 1"), r.get("group"),
                                  r.get("orientation", "v"), r.get("sort", "none"), r.get("xlabel"),
                                  r.get("ylabel"), r.get("unit", ""), r.get("source", ""),
                                  r.get("corners", "editorial"), chrome=True, theme=theme,
                                  grid=r.get("grid", True), markers=r.get("markers", True),
                                  highlights=r.get("highlights") or None)
        unit, dest, note = "bars", args.o or f"{base}.{args.to}", " (layouts: scatter only)"
    elif cmd == "line":
        svg, _, _, n = render_line(r["csv"], r.get("x"), r.get("y"), r.get("title", "Line Trend"),
                                   r.get("subtitle", ""), r.get("figure", "Fig. 1"), r.get("group"),
                                   r.get("xlabel"), r.get("xunit", ""), r.get("ylabel"), r.get("yunit", ""),
                                   r.get("source", ""), r.get("corners", "editorial"), chrome=True, theme=theme,
                                   grid=r.get("grid", True), markers=r.get("markers", True),
                                   highlights=r.get("highlights") or None)
        unit, dest, note = "points", args.o or f"{base}.{args.to}", " (layouts: scatter only)"
    elif cmd in ("flow", "arch", "seq", "schema"):
        spec = load_spec(r["spec"])
        fn = {"flow": render_flow, "arch": render_arch, "seq": render_seq, "schema": render_schema}[cmd]
        if cmd == "flow":
            svg, _, _ = render_flow(spec, r.get("corners", "editorial"), False, theme)
        else:
            svg, _, _ = fn(spec, r.get("corners", "editorial"), theme)
        key = {"flow": "nodes", "arch": "nodes", "seq": "actors", "schema": "tables"}[cmd]
        n = len(spec.get(key, []))
        unit, dest, note = "items", args.o or f"{base}.{args.to}", " (diagram: single layout)"
    elif cmd == "geo":
        svg, _, _, n = render_geo(r["src"], r.get("lat"), r.get("lon"), r.get("label"), r.get("val"),
                                  r.get("title", "Map"), r.get("subtitle", ""), r.get("figure", "Fig. 1"),
                                  r.get("source", ""), theme, chrome=True,
                                  grid=r.get("grid", True), markers=r.get("markers", True),
                                  highlights=r.get("highlights") or None)
        unit, dest, note = "places", args.o or f"{base}.{args.to}", " (map: single layout)"
    else:
        sys.exit(f"unknown receipt cmd '{cmd}'")
    if args.to == "svg":
        with open(dest, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"wrote {dest} ({n} {unit}{note})")
        return
    how = _raster_svg(svg, dest, args.to, args.width)
    if not how:
        sys.exit("PNG/PDF needs Edge, Chrome, or cairosvg. The HTML page also has an Export PNG button.")
    print(f"wrote {dest} via {how} ({n} {unit}{note})")


DESCRIBE = {
    "scatter": {
        "input": "CSV with header row. Two numeric columns minimum.",
        "writes": "py graph.py scatter DATA.csv --x X --y Y -o OUT.html  (+ OUT.svg self-contained, OUT.graph.json receipt)",
        "required": ["--x", "--y"],
        "options": {"--title": "finding, not description", "--subtitle": "one sentence takeaway",
                    "--figure": "Fig. number", "--xlabel/--xunit/--ylabel/--yunit": "axis + unit in parens",
                    "--group": "categorical col, Okabe-Ito legend", "--yerr": "numeric SD/CI col, capped bars",
                    "--facet": "categorical col, small multiples A/B (+col layout via export --layout social)",
                    "--source": "provenance, n auto-appended", "--caption": "kept on the receipt",
                    "--corners": "sharp|rounded|editorial",
                    "--grid/--no-grid": "tick rules, on by default",
                    "--markers/--no-markers": "point dots, on by default",
                    "--highlight": "group or x value, repeatable, drawn larger in accent"},
        "budgets": {"points_rendered": 400, "groups": 8, "facets": 4, "series": "focal rule: 1 accent max"},
        "rules": ["non-negative data never shows a negative axis", "domain includes error bars",
                  "ticks are nice numbers aligned to grid",
                  "title and subtitle are drawn on the figure; the HTML page and the .svg are the same drawing"],
        "example": "py graph.py scatter examples/scatter_groups.csv --x dose --y expr --yerr expr_err --group tissue --facet cohort --xlabel Dose --xunit mg --ylabel Expression --yunit 'log2 counts' -o out/s.html",
    },
    "flow": {
        "input": "JSON spec {title, sub, nodes[], edges[]}",
        "writes": "py graph.py flow SPEC.json -o OUT.html",
        "node": {"id": "unique", "shape": "oval=start/end | rect=step | diamond=decision | dot=merge",
                 "name": "2-4 words", "tag": "STEP|START|END", "sub": "mono sublabel", "rank": "row (default: order)",
                 "lane": "-1 left|0 center|1 right (default 0)", "focal": "bool, max 2 per diagram"},
        "edge": {"from": "id", "to": "id", "label": "ALWAYS label decision exits", "focal": "happy-path bool"},
        "rules": ["top-down; Yes=right, No=down", "diamond ≤3 exits (nest for more)", "orthogonal elbows only",
                  "labels masked with 6px gap", "shape carries type, never color",
                  "no ranks needed: longest-path auto-layering + barycenter uncrossing (--auto forces it)"],
        "budgets": {"nodes": 9, "edges": 12, "focal": 2, "over": "split overview+detail"},
        "example": '{"title":"Deploy approval","nodes":[{"id":"a","shape":"oval","name":"Push"},{"id":"d","shape":"diamond","name":"Risky?","rank":1,"focal":true}],"edges":[{"from":"a","to":"d","label":"pass"}]}',
    },
    "arch": {
        "input": "JSON spec {title, sub, nodes[], edges[]}",
        "writes": "py graph.py arch SPEC.json -o OUT.html",
        "node": {"id": "unique", "layer": "row int (default 0)", "name": "service", "sub": "Lang:port e.g. Go:8080",
                 "tag": "UI|API|SVC|STORE", "focal": "bool, max 2"},
        "edge": {"from": "id", "to": "id", "label": "VERB", "proto": "https=blue arrow", "async": "dashed bool", "focal": "bool"},
        "rules": ["blue=HTTP/API, dashed=async, coral=focal", "tech sublabels in mono, names in sans"],
        "budgets": {"nodes": 9, "edges": 12, "layers": 6, "over": "one view per C4 level"},
    },
    "seq": {
        "input": "JSON spec {title, sub, actors[], messages[]}",
        "writes": "py graph.py seq SPEC.json -o OUT.html",
        "actor": {"id": "unique", "name": "label", "sub": "tech/mono sub", "tag": "USER|UI|GATEWAY|SVC|STORE", "focal": "bool, max 2"},
        "message": {"from": "id", "to": "id", "label": "Call name/payload", "proto": "https/grpc", "reply": "bool dashed", "async": "bool dashed", "focal": "bool"},
        "rules": ["solid=sync, dashed=reply/async, blue=http, coral=focal", "top-down sequence order", "max 6 lifelines"],
        "budgets": {"actors": 6, "messages": 16, "focal": 2, "over": "split into sub-sequences"},
        "example": '{"title":"Auth handshake","actors":[{"id":"u","name":"User"},{"id":"api","name":"API","focal":true}],"messages":[{"from":"u","to":"api","label":"login"}]}',
    },
    "schema": {
        "input": "JSON spec {title, sub, tables[], relations[]}",
        "writes": "py graph.py schema SPEC.json -o OUT.html",
        "table": {"id": "unique", "name": "table_name", "tag": "AUTH|CORE|AUDIT", "focal": "bool, max 2",
                  "columns": [{"name": "col", "type": "data_type", "pk": "bool", "fk": "bool", "unique": "bool"}]},
        "relation": {"from": "id", "from_col": "col", "to": "id", "to_col": "col", "label": "1:N|1:1|M:N", "focal": "bool"},
        "rules": ["PK coral badge, FK blue badge, columns in mono, types muted", "orthogonal elbow routing", "max 6 tables per view"],
        "budgets": {"tables": 6, "relations": 10, "columns_per_table": 12, "over": "split by bounded context"},
        "example": '{"title":"Users & Teams","tables":[{"id":"u","name":"users","columns":[{"name":"id","type":"uuid","pk":true}]}],"relations":[]}',
    },
    "bar": {
        "input": "CSV with header row. One categorical column and one numeric column.",
        "writes": "py graph.py bar DATA.csv --cat CAT --val VAL -o OUT.html",
        "options": {"--cat": "category column", "--val": "numeric value column", "--group": "subgroup column",
                    "--sort": "none|asc|desc", "--orientation": "v|h", "--unit": "unit string",
                    "--title/--subtitle": "drawn on the figure",
                    "--grid/--no-grid": "tick rules, on by default",
                    "--markers/--no-markers": "value labels, on by default",
                    "--highlight": "category or group, repeatable, drawn in accent"},
        "budgets": {"bars": 24, "categories": 12, "over": "sort top-N + other"},
        "rules": ["bar charts must start at zero", "value labels sit on the bars", "gridlines follow the ticks"],
        "example": "py graph.py bar examples/bar_latency.csv --cat service --val p99_latency_ms --unit ms -o out/bar.html",
    },
    "line": {
        "input": "CSV with header row. Continuous/temporal X column and numeric Y column.",
        "writes": "py graph.py line DATA.csv --x X --y Y -o OUT.html",
        "options": {"--x": "x column (numeric or timestamp)", "--y": "y column (numeric)", "--group": "series column",
                    "--xlabel/--xunit/--ylabel/--yunit": "axis labels",
                    "--title/--subtitle": "drawn on the figure",
                    "--grid/--no-grid": "tick rules, on by default",
                    "--markers/--no-markers": "point dots, on by default",
                    "--highlight": "x value or group, repeatable, drawn larger in accent"},
        "budgets": {"series": 6, "points_per_series": 200, "over": "downsample or facet"},
        "rules": ["non-negative data floors at 0", "Okabe-Ito series colors", "subtle area fill under lines"],
        "example": "py graph.py line examples/line_throughput.csv --x timestamp --y rps --group service -o out/line.html",
    },
    "geo": {
        "input": "CSV with lat/lon columns, or a GeoJSON FeatureCollection of Points and Polygons.",
        "writes": "py graph.py geo DATA.csv --lat lat --lon lon --label name --val pop -o OUT.html",
        "options": {"--lat/--lon": "column names (guessed from lat/lon/lng when omitted)",
                    "--label": "place name", "--val": "numeric size",
                    "--title/--subtitle": "drawn on the figure", "--source": "footer provenance",
                    "--grid/--no-grid": "graticule lines, on by default",
                    "--markers/--no-markers": "place dots, on by default",
                    "--highlight": "place name, repeatable, drawn larger in accent"},
        "budgets": {"points": 400, "over": "crop to the region you mean"},
        "rules": ["Web Mercator figure with a built-in coastline, not a tiled basemap",
                  "GeoJSON polygons are drawn on top of the coastline",
                  "graticule, kilometre scale bar, north arrow", "dot size follows --val"],
        "example": "py graph.py geo examples/geo_cities.csv --lat lat --lon lon --label city --val people_m -o out/geo.html",
    },
    "doc": {
        "input": "Markdown document containing ```graph:<type> fenced blocks.",
        "writes": "py graph.py doc DOC.md [--out-dir assets] [--check]",
        "behavior": "Parses and compiles embedded diagram specs into standalone SVGs in assets/, updates doc links",
    },
    "monitor": {
        "input": "Repository working tree or git history.",
        "writes": "py graph.py monitor [--base <ref>] [--ci] [--map graph.monitor.json]",
        "behavior": "Scans code changes for data models, routes, and migrations without corresponding diagram updates; outputs JSON drift report. With --map, extracts each changed file and semantically diffs against its spec (no diff = no drift, even if files changed).",
        "map_format": '{"mappings": [{"code": "models/*.py", "spec": "docs/schema.graph.json", "kind": "schema", "domain": "database"}]}',
    },
    "extract": {
        "input": "Code source file (.sql DDL, Python ORM model, FastAPI routes).",
        "writes": "py graph.py extract schema|routes SOURCE_FILE -o SPEC.json",
        "behavior": "Reverse-extracts architecture or database schema diagram specs directly from source code using AST/token parsing",
    },
    "export": {
        "input": "Receipt OUT.graph.json written beside every render.",
        "writes": "py graph.py export OUT --to png|pdf|svg [--layout figure|wide|slide|social] [--width 1600] [-o FILE]",
        "rules": ["svg works everywhere, zero deps (re-render from receipt)",
                  "layouts figure/wide/slide/social apply to scatter; other types export single layout",
                  "png and pdf use cairosvg when it imports, otherwise headless Edge or Chrome",
                  "the HTML page has Export PNG, which saves the figure from the browser"],
        "budgets": {"png_width_default": 1600},
        "example": "py graph.py export out/scatter --to svg --layout social",
    },
    "sync": {
        "input": "Same inputs as monitor (--path, --base, --map).",
        "writes": "py graph.py sync --map graph.monitor.json [--docs ARCH.md] [--commit]",
        "behavior": "Auto-fix bot: for each mapping-backed drift entry runs extract -o spec, validates, recompiles --docs, audits emitted SVGs. Default touches only the working tree; --commit creates a LOCAL commit (never pushes). Exit 1 if anything is left undone. Heartbeat: cron `0 6 * * * cd repo && py graph.py sync --map graph.monitor.json --commit`, Windows Task Scheduler, or an Antigravity cron//goal task.",
    },
}


def do_describe(args):
    print(json.dumps(DESCRIBE[args.type], indent=2) if args.type else json.dumps({"types": sorted(DESCRIBE)}, indent=2))


def _vissue(errors, warnings, code, msg, fix=""):
    (errors if code == "E" else warnings).append({"msg": msg, "fix": fix} if fix else {"msg": msg})


def do_validate(args):
    errors, warnings = [], []
    if args.target.endswith(".csv"):
        import csv as _csv
        try:
            with open(args.target, newline="", encoding="utf-8") as f:
                rd = _csv.DictReader(f)
                cols, rows = rd.fieldnames or [], list(rd)
        except FileNotFoundError:
            print(json.dumps({"ok": False, "errors": [{"msg": f"file not found: {args.target}"}], "warnings": []})); raise SystemExit(1)
        if not cols:
            errors.append({"msg": "no header row"})
        else:
            vtype = getattr(args, "type", "scatter") or "scatter"
            if vtype == "bar":
                cat, val = args.x, args.y
                if cat and cat not in cols:
                    _vissue(errors, warnings, "E", f"category column '{cat}' not in {cols}", f"use one of {cols}")
                if val and (val not in cols or not all(_numok(r.get(val, "")) for r in rows[:50] if (r.get(val) or "") != "")):
                    _vissue(errors, warnings, "E", f"value column '{val}' missing or non-numeric", "pick a numeric column")
                if cat in (cols or []) and len({r[cat] for r in rows}) > 12:
                    warnings.append({"msg": f"{len({r[cat] for r in rows})} categories > 12", "fix": "sort top-11 + Other"})
                if len(rows) > 24:
                    warnings.append({"msg": f"{len(rows)} bars > 24", "fix": "aggregate or top-N"})
            elif vtype == "geo":
                lon, lat = args.x, args.y
                if not lon:
                    lon = next((c for c in cols if c.lower() in ("lon", "lng", "long", "longitude")), None)
                if not lat:
                    lat = next((c for c in cols if c.lower() in ("lat", "latitude")), None)
                if not lon or lon not in cols or not lat or lat not in cols:
                    _vissue(errors, warnings, "E", f"need lat and lon columns, got {cols}", "pass --x lon --y lat")
                else:
                    bad = 0
                    for row in rows:
                        try:
                            la, lo = float(row[lat]), float(row[lon])
                            if not (-90 <= la <= 90 and -180 <= lo <= 180):
                                bad += 1
                        except (TypeError, ValueError):
                            bad += 1
                    if bad:
                        _vissue(errors, warnings, "E", f"{bad} rows with bad lat/lon", "lat -90..90, lon -180..180")
                    if len(rows) > 400:
                        warnings.append({"msg": f"n={len(rows)} points", "fix": "aggregate to the area you want to show"})
            elif vtype == "line":
                if args.x and args.x not in cols:
                    _vissue(errors, warnings, "E", f"x column '{args.x}' not in {cols}", f"use one of {cols}")
                if args.y and (args.y not in cols or not all(_numok(r.get(args.y, "")) for r in rows[:50] if (r.get(args.y) or "") != "")):
                    _vissue(errors, warnings, "E", f"y column '{args.y}' missing or non-numeric", "pick a numeric column")
                if args.group and args.group in cols and len({r[args.group] for r in rows}) > 6:
                    warnings.append({"msg": f"{len({r[args.group] for r in rows})} series > 6", "fix": "keep top series"})
                if len(rows) > 400:
                    warnings.append({"msg": f"n={len(rows)} points, over budget", "fix": "downsample or facet"})
            else:
                for c in (args.x, args.y):
                    if c and c not in cols:
                        _vissue(errors, warnings, "E", f"column '{c}' not in {cols}", f"use one of {cols}")
                num = [c for c in cols if all(_numok(r.get(c, "")) for r in rows[:50] if r.get(c, "") != "")]
                if len(num) < 2:
                    _vissue(errors, warnings, "E", f"need 2 numeric cols, found {num}", "check delimiter/headers")
                if len(rows) > 400:
                    warnings.append({"msg": f"n={len(rows)} > 400 rendered (rest truncated)", "fix": "aggregate or --facet split"})
                for c in (args.group, args.facet):
                    if c and c in cols and len({r[c] for r in rows}) > 8:
                        warnings.append({"msg": f"'{c}' has {len({r[c] for r in rows})} distinct values", "fix": "keep top-7 + Other"})
    else:
        try:
            spec = load_spec(args.target)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(json.dumps({"ok": False, "errors": [{"msg": f"unreadable spec: {e}"}], "warnings": []})); raise SystemExit(1)
        _validate_spec_dict(spec, errors, warnings)
    ok = not errors
    print(json.dumps({"ok": ok, "errors": errors, "warnings": warnings}, indent=2))
    raise SystemExit(0 if ok else 1)


def _validate_spec_dict(spec, errors, warnings):
    """Shared diagram-spec checks for `validate` + `doc`. Appends E/W dicts."""
    if "actors" in spec or "messages" in spec:
        actors, messages = spec.get("actors", []), spec.get("messages", [])
        a_ids = [a.get("id") for a in actors]
        if len(set(a_ids)) != len(a_ids):
            _vissue(errors, warnings, "E", "duplicate actor ids", "make actor ids unique")
        if len(actors) > 6:
            _vissue(errors, warnings, "E", f"{len(actors)} actors > budget 6", "split into sub-sequences")
        if len(messages) > 16:
            _vissue(errors, warnings, "E", f"{len(messages)} messages > budget 16", "focus on primary handshake")
        if sum(1 for a in actors if a.get("focal")) > 2:
            _vissue(errors, warnings, "E", "focal on >2 actors erases signal", "max 2 focal actors")
        for m in messages:
            for k in ("from", "to"):
                if m.get(k) not in a_ids:
                    _vissue(errors, warnings, "E", f"message refs unknown actor '{m.get(k)}'", f"use one of {a_ids}")
    elif "tables" in spec or "relations" in spec:
        tables, relations = spec.get("tables", []), spec.get("relations", [])
        t_ids = [t.get("id") for t in tables]
        if len(set(t_ids)) != len(t_ids):
            _vissue(errors, warnings, "E", "duplicate table ids", "make table ids unique")
        if len(tables) > 6:
            _vissue(errors, warnings, "E", f"{len(tables)} tables > budget 6", "split into bounded context views")
        if sum(1 for t in tables if t.get("focal")) > 2:
            _vissue(errors, warnings, "E", "focal on >2 tables erases signal", "max 2 focal tables")
        for t in tables:
            cols = t.get("columns", [])
            if len(cols) > 12:
                warnings.append({"msg": f"table '{t.get('id')}' has {len(cols)} columns (>12)", "fix": "hide non-essential columns"})
        for rel in relations:
            if rel.get("from") not in t_ids or rel.get("to") not in t_ids:
                _vissue(errors, warnings, "E", "relation refs unknown table", f"use one of {t_ids}")
    else:
        nodes, edges = spec.get("nodes", []), spec.get("edges", [])
        ids = [n.get("id") for n in nodes]
        if len(set(ids)) != len(ids):
            _vissue(errors, warnings, "E", "duplicate node ids", "make ids unique")
        for e in edges:
            for k in ("from", "to"):
                if e.get(k) not in ids:
                    _vissue(errors, warnings, "E", f"edge {e} refs unknown id '{e.get(k)}'",
                            f"add node or fix to one of {ids}")
        if len(nodes) > 9:
            _vissue(errors, warnings, "E", f"{len(nodes)} nodes > budget 9", "split into overview + detail views")
        if len(edges) > 12:
            _vissue(errors, warnings, "E", f"{len(edges)} edges > budget 12", "drop obvious-from-layout arrows")
        if sum(1 for n in nodes if n.get("focal")) > 2:
            _vissue(errors, warnings, "E", "focal on >2 nodes erases signal", "keep 1-2 focal, demote rest")
        from collections import Counter
        outdeg = Counter(e["from"] for e in edges if "from" in e)
        shapes = {n["id"]: n.get("shape", "rect") for n in nodes}
        for nid, deg in outdeg.items():
            if shapes.get(nid) == "diamond" and deg > 3:
                _vissue(errors, warnings, "E", f"diamond '{nid}' has {deg} exits", "nest diamonds")
            for e in edges:
                if shapes.get(e.get("from")) == "diamond" and not e.get("label"):
                    warnings.append({"msg": f"unlabeled exit from diamond '{e.get('from')}'", "fix": "label Yes/No or condition"})


def _numok(v):
    try:
        float(v); return True
    except (ValueError, TypeError):
        return False


def do_infer(args):
    import csv as _csv
    with open(args.target, newline="", encoding="utf-8") as f:
        rd = _csv.DictReader(f)
        cols, rows = rd.fieldnames or [], list(rd)
    numeric = [c for c in cols if rows and all(_numok(r.get(c, "")) for r in rows[:50] if (r.get(c) or "") != "")]
    cats = {}
    for c in cols:
        if c not in numeric:
            vals = sorted({r[c] for r in rows if r.get(c)})
            if 1 < len(vals) <= 12:
                cats[c] = vals
    err = next((c for c in cols if any(k in c.lower() for k in ("err", "sd", "_sd", "ci", "sem")) and c in numeric), None)
    nums = [c for c in numeric if c != err]
    if len(nums) < 2:
        print(json.dumps({"ok": False, "fix": "need 2 numeric columns", "columns": cols})); raise SystemExit(1)
    ck = list(cats)
    group = ck[0] if ck and len(cats[ck[0]]) <= 8 else None
    facet = next((c for c in ck[1:] if len(cats[c]) <= 4), None)
    name = os.path.splitext(os.path.basename(args.target))[0].replace("_", " ")
    out = {"ok": True, "cmd": "scatter", "csv": args.target, "x": nums[0], "y": nums[1],
           "title": name.capitalize(), "subtitle": "", "figure": "Fig. 1",
           "xlabel": nums[0], "xunit": "", "ylabel": nums[1], "yunit": "",
           "group": group, "yerr": err, "facet": facet, "source": os.path.basename(args.target),
           "groups_found": {k: v for k, v in cats.items()},
           "render": f"py graph.py scatter {args.target} --x {nums[0]} --y {nums[1]}"
                     + (f" --group {group}" if group else "") + (f" --yerr {err}" if err else "")
                     + (f" --facet {facet}" if facet else "") + " -o out/inferred.html",
           "next": "edit title/subtitle/units, then validate + render"}
    print(json.dumps(out, indent=2))


def do_audit(args):
    import re, xml.etree.ElementTree as ET
    errors, warnings = [], []
    p = args.target
    raw = open(p, encoding="utf-8").read()
    m = re.search(r"<svg[\s\S]*?</svg>", raw)
    svg = m.group(0) if m else raw
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as e:
        print(json.dumps({"ok": False, "errors": [{"msg": f"malformed SVG: {e}"}], "warnings": []})); raise SystemExit(1)
    W = H = 0
    vb = root.get("viewBox", "").split()
    if len(vb) == 4:
        W, H = float(vb[2]), float(vb[3])
    def _tagged(name):
        return [el for el in root.iter() if str(el.tag).split("}")[-1] == name]
    texts = _tagged("text")
    if not any(t.get("font-size") == "24" for t in texts) and not _tagged("title"):
        errors.append({"msg": "no <title>: figure unnamed for AT/docs"})
    if not _tagged("desc"):
        warnings.append({"msg": "no <desc>: add one-sentence content summary"})
    if re.search(r"font-family='[^\"\]]", svg):
        errors.append({"msg": "unquoted font-family attribute", "fix": 'wrap families: font-family="\'Inter\',sans-serif"'})
    if sum(1 for t in texts if t.get("font-size") == "24") > 1:
        warnings.append({"msg": "2+ hero titles inside one figure", "fix": "title once (page XOR figure)"})
    neg = [t.text for t in texts if (t.text or "").strip().startswith("-") and re.fullmatch(r"-\d[\d.,k]*", (t.text or "").strip())]
    if neg:
        warnings.append({"msg": f"negative ticks {neg}", "fix": "verify intended; ratio data floors at 0"})
    circles = len(_tagged("circle"))
    if circles > 400:
        warnings.append({"msg": f"{circles} points over render budget", "fix": "aggregate/facet"})
    for t in texts:
        try:
            x = float(t.get("x", "0").split()[0])
            if (x < -4 or (W and x > W + 4)) and t.get("text-anchor") != "middle":
                warnings.append({"msg": f"text '{(t.text or '')[:20]}' near canvas edge x={x}", "fix": "check clipping"})
                break
        except ValueError:
            pass
    dup = [t.text for t in texts if t.text]
    from collections import Counter
    for txt, c in Counter(dup).items():
        if c > 3 and len(txt) > 8:
            warnings.append({"msg": f"'{txt[:30]}' repeated {c}x", "fix": "dedupe title/caption/source"})
            break
    ok = not errors
    print(json.dumps({"ok": ok, "errors": errors, "warnings": warnings,
                      "stats": {"texts": len(texts), "points": circles, "canvas": [W, H]}}, indent=2))
    raise SystemExit(0 if ok else 1)


def _inject_links(content, items):
    """Idempotent figure-link injection after each fence. Re-run safe:
    an existing anchor+link pair for the id is replaced, never duplicated."""
    import re
    for end, diag_id, title, rel in sorted(items, reverse=True):
        safe = title.replace("[", "").replace("]", "")
        anchor = f"<!-- graph:{diag_id} -->\n![{safe}]({rel})"
        tail = content[end:]
        m2 = re.match(r"\n?<!-- graph:" + re.escape(diag_id) + r" -->\n!\[[^\]]*\]\([^)\s]*\)", tail)
        if m2:
            content = content[:end] + "\n" + anchor + tail[m2.end():]
        else:
            content = content[:end] + "\n" + anchor + tail
    return content


def do_doc(args):
    import re, hashlib
    target = args.target
    if not os.path.exists(target):
        sys.exit(f"doc target not found: {target}")
    with open(target, encoding="utf-8") as f:
        content = f.read()
    pattern = re.compile(r"```(?:graph|graph-spec):([a-zA-Z0-9_-]+)(?:[ \t]+([^\n]*))?\n([\s\S]*?)```")
    matches = list(pattern.finditer(content))
    if not matches:
        print(f"{target}: no ```graph:<type> blocks found")
        return
    base_dir = os.path.dirname(os.path.abspath(target))
    out_dir = args.out_dir or os.path.join(base_dir, "assets")
    if not args.check:  # --check is strictly read-only (CI)
        os.makedirs(out_dir, exist_ok=True)
    count, errs, injections = 0, 0, []
    for idx, m in enumerate(matches):
        kind = m.group(1).lower()
        meta = m.group(2) or ""
        body = m.group(3).strip()
        diag_id = f"diagram_{idx+1}"
        title = kind.capitalize()
        id_m = re.search(r'id="([^"]+)"', meta)
        if id_m:
            diag_id = id_m.group(1)
        t_m = re.search(r'title="([^"]+)"', meta)
        if t_m:
            title = t_m.group(1)
        ve, vw = [], []
        try:
            if kind in ("arch", "flow", "seq", "schema"):
                spec = json.loads(body) if body.startswith("{") else (yaml.safe_load(body) if HAS_YAML else json.loads(body))
                if "title" not in spec:
                    spec["title"] = title
                _validate_spec_dict(spec, ve, vw)  # validate BEFORE render
                if ve:
                    raise ValueError("validate: " + "; ".join(d["msg"] for d in ve))
                if kind == "flow":
                    svg, _, _ = render_flow(spec)
                elif kind == "arch":
                    svg, _, _ = render_arch(spec)
                elif kind == "seq":
                    svg, _, _ = render_seq(spec)
                elif kind == "schema":
                    svg, _, _ = render_schema(spec)
                out_svg = os.path.join(out_dir, f"{diag_id}.svg")
                digest = hashlib.sha1(svg.encode("utf-8")).hexdigest()
                if args.check:
                    if not os.path.exists(out_svg):
                        print(f"  [missing] {diag_id} ({kind}): run without --check first")
                        errs += 1
                    elif hashlib.sha1(open(out_svg, encoding="utf-8").read().encode("utf-8")).hexdigest() != digest:
                        print(f"  [stale] {diag_id} ({kind}): {out_svg} differs from spec")
                        errs += 1
                    else:
                        print(f"  [ok] {diag_id} ({kind})")
                        count += 1
                else:
                    with open(out_svg, "w", encoding="utf-8") as sf:
                        sf.write(svg)
                    count += 1
                    print(f"  [compiled] {kind} -> {out_svg}")
                    rel = os.path.relpath(out_svg, base_dir).replace(os.sep, "/")
                    injections.append((m.end(), diag_id, title, rel))
            else:
                errs += 1
                print(f"  [skip] {diag_id}: unknown kind '{kind}'", file=sys.stderr)
        except Exception as e:
            errs += 1
            print(f"  [error] {diag_id} ({kind}): {e}", file=sys.stderr)
    if injections and not args.check:
        with open(target, "w", encoding="utf-8") as f:
            f.write(_inject_links(content, injections))
        print(f"doc: figure links synced in {target}")
    print(f"doc: processed {count} diagrams ({errs} errors)")
    if errs > 0:
        raise SystemExit(1)


def _split_ddl(body):
    """Split a CREATE TABLE body on commas at paren-depth 0 (DECIMAL(10,2) safe).
    Handles packed single-line and one-column-per-line DDL alike."""
    parts, depth, cur = [], 0, []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def do_extract(args):
    import re, ast
    src = args.source
    if not os.path.exists(src):
        sys.exit(f"source file not found: {src}")
    with open(src, encoding="utf-8") as f:
        code = f.read()
    if args.o:
        parent = os.path.dirname(os.path.abspath(args.o))
        os.makedirs(parent, exist_ok=True)
    if args.ext_type == "schema":
        tables, relations = [], []
        if src.endswith(".sql"):
            tbl_matches = re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)\s*\(([\s\S]*?)\);", code, re.IGNORECASE)
            for tm in tbl_matches:
                tname = tm.group(1)
                body = tm.group(2)
                cols = []
                for line in _split_ddl(body):
                    line = line.strip()
                    if not line or line.upper().startswith(("PRIMARY KEY", "FOREIGN KEY", "CONSTRAINT", "INDEX", "UNIQUE")):
                        fk_m = re.search(r"FOREIGN\s+KEY\s*\(([a-zA-Z0-9_]+)\)\s*REFERENCES\s*([a-zA-Z0-9_]+)\s*\(([a-zA-Z0-9_]+)\)", line, re.IGNORECASE)
                        if fk_m:
                            relations.append({"from": fk_m.group(2), "from_col": fk_m.group(3), "to": tname, "to_col": fk_m.group(1), "label": "1:N"})
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        cname, ctype = parts[0], parts[1]
                        is_pk = "PRIMARY KEY" in line.upper()
                        cols.append({"name": cname, "type": ctype, "pk": is_pk})
                tables.append({"id": tname, "name": tname, "columns": cols})
        elif src.endswith(".prisma"):
            scalars = {"String", "Boolean", "Int", "BigInt", "Float", "Decimal", "DateTime", "Json", "Bytes"}
            for mm in re.finditer(r"model\s+([a-zA-Z0-9_]+)\s*\{([^}]*)\}", code):
                tname, cols = mm.group(1).lower(), []
                for line in mm.group(2).split("\n"):
                    line = line.strip()
                    if not line or line.startswith(("@@", "//")):
                        continue
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    cname, ctype, rest = parts[0], parts[1].rstrip("?"), " ".join(parts[2:])
                    col = {"name": cname, "type": parts[1],
                           "pk": "@id" in rest, "unique": "@unique" in rest}
                    cols.append(col)
                    if ctype not in scalars:
                        # object-side relation field: Team @relation(fields:[fk], references:[pk])
                        fm = re.search(r"fields\s*:\s*\[([a-zA-Z0-9_]+)\]", rest)
                        pm = re.search(r"references\s*:\s*\[([a-zA-Z0-9_]+)\]", rest)
                        if fm and pm:
                            relations.append({"from": ctype.lower(), "from_col": pm.group(1),
                                              "to": tname, "to_col": fm.group(1), "label": "1:N"})
                if cols:
                    tables.append({"id": tname, "name": mm.group(1), "columns": cols[:12]})
        elif src.endswith(".py"):
            try:
                tree = ast.parse(code)

                def _call_name(call):
                    f = call.func
                    if isinstance(f, ast.Attribute):
                        return f.attr
                    return getattr(f, "id", "")

                def _kw_true(call, names):
                    return any(k.arg in names and isinstance(k.value, ast.Constant) and k.value.value is True
                               for k in call.keywords)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        tname = node.name.lower()
                        for _tn in node.body:  # SQLAlchemy reality: table name wins over class name
                            if isinstance(_tn, ast.Assign):
                                for _t in _tn.targets:
                                    if isinstance(_t, ast.Name) and _t.id == "__tablename__" \
                                            and isinstance(_tn.value, ast.Constant):
                                        tname = str(_tn.value.value)
                        is_django = any("Model" in ast.unparse(b) for b in node.bases) if hasattr(ast, "unparse") else False
                        cols = []
                        for item in node.body:
                            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                                cname = item.target.id
                                if cname.startswith("__"):
                                    continue
                                ctype = ast.unparse(item.annotation) if hasattr(ast, "unparse") else "any"
                                col = {"name": cname, "type": ctype, "pk": cname.lower() == "id"}
                                cols.append(col)
                                if isinstance(item.value, ast.Call):  # SQLModel: Field(foreign_key="t.c")
                                    for k in item.value.keywords:
                                        if k.arg == "foreign_key" and isinstance(k.value, ast.Constant) \
                                                and "." in str(k.value.value):
                                            ref = str(k.value.value).split(".")
                                            col["fk"] = True
                                            relations.append({"from": ref[0], "from_col": ref[1],
                                                              "to": tname, "to_col": cname, "label": "1:N"})
                            elif isinstance(item, ast.Assign) and isinstance(item.value, ast.Call):
                                call = item.value
                                fname = _call_name(call)
                                django_field = fname in ("CharField", "TextField", "IntegerField", "BigIntegerField",
                                                         "FloatField", "DecimalField", "BooleanField", "DateField",
                                                         "DateTimeField", "UUIDField", "EmailField", "ForeignKey",
                                                         "OneToOneField", "ManyToManyField", "AutoField", "BigAutoField")
                                if is_django or django_field:
                                    for tgt in item.targets:
                                        if not isinstance(tgt, ast.Name):
                                            continue
                                        cname = tgt.id
                                        if fname in ("ForeignKey", "OneToOneField"):
                                            arg0 = call.args[0] if call.args else None
                                            target = ""
                                            if isinstance(arg0, ast.Constant):
                                                target = str(arg0.value).split(".")[-1]
                                            elif isinstance(arg0, ast.Name):
                                                target = arg0.id
                                            cols.append({"name": cname, "type": fname, "pk": _kw_true(call, ("primary_key",))})
                                            if target and target.lower() != "self":
                                                relations.append({"from": target.lower(), "from_col": "id",
                                                                  "to": tname, "to_col": cname, "label": "1:N"})
                                        elif fname != "ManyToManyField":
                                            cols.append({"name": cname, "type": fname,
                                                         "pk": _kw_true(call, ("primary_key",)) or cname.lower() == "id"})
                                else:
                                    for tgt in item.targets:
                                        if not isinstance(tgt, ast.Name) or tgt.id.startswith("__"):
                                            continue
                                        cname = tgt.id
                                        ctype, fk_hit = "column", None
                                        for a in list(call.args) + [k.value for k in call.keywords]:
                                            if isinstance(a, ast.Call) and _call_name(a) == "ForeignKey" and a.args:
                                                ref = a.args[0]
                                                if isinstance(ref, ast.Constant) and "." in str(ref.value):
                                                    fk_hit = str(ref.value).split(".")
                                            elif isinstance(a, ast.Name):
                                                ctype = a.id
                                            elif isinstance(a, ast.Attribute):
                                                ctype = a.attr
                                        col = {"name": cname, "type": ctype,
                                               "pk": _kw_true(call, ("primary_key",)) or cname.lower() == "id"}
                                        cols.append(col)
                                        if fk_hit:
                                            col["fk"] = True
                                            relations.append({"from": fk_hit[0], "from_col": fk_hit[1],
                                                              "to": tname, "to_col": cname, "label": "1:N"})
                        if cols:
                            tables.append({"id": tname, "name": node.name, "columns": cols[:10]})
            except Exception as e:
                sys.exit(f"AST parse failed: {e}")
        for rel in relations:  # back-mark FK columns so badges render
            for tbl in tables:
                if tbl["id"] == rel["to"]:
                    for col in tbl["columns"]:
                        if col["name"] == rel["to_col"]:
                            col["fk"] = True
        spec = {"title": f"Schema from {os.path.basename(src)}", "sub": "Auto-extracted database schema", "tables": tables, "relations": relations}
        if args.o:
            with open(args.o, "w", encoding="utf-8") as f:
                json.dump(spec, f, indent=2)
            print(f"wrote extracted schema to {args.o} ({len(tables)} tables)")
        else:
            print(json.dumps(spec, indent=2))
    elif args.ext_type == "routes":
        nodes = [{"id": "client", "name": "Client", "tag": "USER", "layer": 0}]
        edges = []
        routes = re.findall(r'@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']', code, re.IGNORECASE)
        for method, path in routes[:8]:
            rid = re.sub(r'[^a-zA-Z0-9_]', '_', path).strip('_') or "root"
            nodes.append({"id": rid, "name": path, "sub": method.upper(), "tag": "API", "layer": 1})
            edges.append({"from": "client", "to": rid, "label": method.upper(), "proto": "https"})
        spec = {"title": f"Routes from {os.path.basename(src)}", "sub": "Auto-extracted API routes", "nodes": nodes, "edges": edges}
        if args.o:
            with open(args.o, "w", encoding="utf-8") as f:
                json.dump(spec, f, indent=2)
            print(f"wrote extracted routes to {args.o} ({len(nodes)} nodes)")
        else:
            print(json.dumps(spec, indent=2))


def _merge_specs(specs, kind):
    """Union per-file extractions (models/*.py is many files, one diagram)."""
    if kind == "schema":
        tables, rels, seen = {}, [], set()
        for s in specs:
            for t in s.get("tables", []):
                tables.setdefault(t["id"], t)
            for r in s.get("relations", []):
                k = (r.get("from"), r.get("from_col"), r.get("to"), r.get("to_col"))
                if k not in seen:
                    seen.add(k)
                    rels.append(r)
        return {"tables": list(tables.values()), "relations": rels}
    nodes, edges, nseen, eseen = [], [], set(), set()
    for s in specs:
        for n in s.get("nodes", []):
            if n.get("id") not in nseen:
                nseen.add(n["id"])
                nodes.append(n)
        for e in s.get("edges", []):
            k = (e.get("from"), e.get("to"), e.get("label"))
            if k not in eseen:
                eseen.add(k)
                edges.append(e)
    return {"nodes": nodes, "edges": edges}


def _spec_diff(existing, fresh, kind):
    """Semantic diff (layout-blind): '' = in sync, else human summary."""
    bits = []
    if kind == "schema":
        old = {t["id"]: {c["name"]: c.get("type", "") for c in t.get("columns", [])} for t in existing.get("tables", [])}
        new = {t["id"]: {c["name"]: c.get("type", "") for c in t.get("columns", [])} for t in fresh.get("tables", [])}
        for tid in sorted(set(new) - set(old)):
            bits.append(f"Added table '{tid}'")
        for tid in sorted(set(old) - set(new)):
            bits.append(f"Removed table '{tid}'")
        for tid in sorted(set(old) & set(new)):
            o, n = old[tid], new[tid]
            for c in sorted(set(n) - set(o)):
                bits.append(f"table '{tid}': +column '{c}'")
            for c in sorted(set(o) - set(n)):
                bits.append(f"table '{tid}': -column '{c}'")
            for c in sorted(set(o) & set(n)):
                if o[c] != n[c]:
                    bits.append(f"table '{tid}': ~column '{c}' ({o[c]}→{n[c]})")
    else:
        old_n = {n.get("id") for n in existing.get("nodes", [])}
        new_n = {n.get("id") for n in fresh.get("nodes", [])}
        old_e = {(e.get("from"), e.get("to")) for e in existing.get("edges", [])}
        new_e = {(e.get("from"), e.get("to")) for e in fresh.get("edges", [])}
        for i in sorted(new_n - old_n):
            bits.append(f"Added node '{i}'")
        for i in sorted(old_n - new_n):
            bits.append(f"Removed node '{i}'")
        for a, b in sorted(new_e - old_e):
            bits.append(f"Added edge {a}->{b}")
        for a, b in sorted(old_e - new_e):
            bits.append(f"Removed edge {a}->{b}")
    return "; ".join(bits[:12])


def do_sync(args):
    """Auto-fix bot (plan Mode 3): monitor -> extract -> validate -> doc ->
    audit, optionally commit. Default touches only the working tree; --commit
    creates a local commit (never pushes). Exit 1 if anything is left undone."""
    import re as _re
    import subprocess as _sp
    path = args.path or "."
    me = os.path.abspath(__file__)
    mon = [sys.executable, me, "monitor", "--path", path, "--base", args.base or "HEAD"]
    if args.map:
        mon += ["--map", args.map]
    r = _sp.run(mon, capture_output=True, text=True)
    try:
        rep = json.loads(r.stdout)
    except json.JSONDecodeError:
        sys.exit(f"sync: monitor produced no report:\n{r.stdout}\n{r.stderr}")
    synced, failed = [], []
    for item in rep.get("stale_domains", []):
        spec = item.get("diagram_spec", "")
        m = _re.match(r"py graph\.py extract (\w+) (\S+) -o (\S+)", item.get("remediation_cmd", ""))
        if not spec or not m:
            failed.append({"spec": spec or item.get("domain", "?"),
                           "reason": "heuristic-only finding: add a --map mapping for machine remediation"})
            continue
        kind, src, _ = m.groups()
        p1 = _sp.run([sys.executable, me, "extract", kind, os.path.join(path, src),
                      "-o", os.path.join(path, spec)], capture_output=True, text=True)
        if p1.returncode:
            failed.append({"spec": spec, "reason": (p1.stderr.strip() or "extract failed")[-200:]})
            continue
        p2 = _sp.run([sys.executable, me, "validate", os.path.join(path, spec)],
                      capture_output=True, text=True)
        if p2.returncode:
            failed.append({"spec": spec, "reason": "extracted spec fails validate"})
            continue
        ok_all, audited = True, []
        for d in (args.docs or []):
            dp = d if os.path.isabs(d) else os.path.join(path, d)
            p3 = _sp.run([sys.executable, me, "doc", dp], capture_output=True, text=True)
            if p3.returncode:
                failed.append({"spec": spec, "reason": f"doc failed on {d}"})
                ok_all = False
                break
            for line in p3.stdout.splitlines():
                mm = _re.search(r"\[compiled\] \w+ -> (.+)", line)
                if mm:
                    pa = _sp.run([sys.executable, me, "audit", mm.group(1).strip()],
                                  capture_output=True, text=True)
                    audited.append(mm.group(1).strip())
                    if pa.returncode:
                        failed.append({"spec": spec, "reason": f"audit failed: {mm.group(1).strip()}"})
                        ok_all = False
                        break
            if not ok_all:
                break
        if ok_all:
            synced.append({"spec": spec, "diff": item.get("diff_summary", ""), "audited": audited})
    committed = False
    if args.commit and synced and not failed:
        g = _sp.run(["git", "-C", path, "status", "--porcelain"], capture_output=True, text=True)
        if g.returncode == 0 and g.stdout.strip():
            names = ", ".join(s["spec"] for s in synced)
            c2 = _sp.run(["git", "-C", path, "add", "-A"], capture_output=True, text=True)
            c3 = _sp.run(["git", "-C", path, "-c", "user.email=graph-bot", "-c", "user.name=graph-sync",
                          "commit", "-m", f"chore(docs): synchronize architecture diagrams ({names})"],
                         capture_output=True, text=True)
            committed = c2.returncode == 0 and c3.returncode == 0
    out = {"ok": not failed, "synced": synced, "failed": failed, "committed": committed}
    print(json.dumps(out, indent=2))
    raise SystemExit(0 if not failed else 1)


def do_monitor(args):
    import subprocess
    path = args.path or "."
    base = args.base or "HEAD"
    changed_files = []
    try:
        if base == "HEAD":
            # local mode: uncommitted working-tree state (tracked mods + untracked)
            r = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=path, capture_output=True, text=True)
            if r.returncode == 0:
                changed_files = [f.strip() for f in r.stdout.splitlines() if f.strip()]
            r2 = subprocess.run(["git", "status", "--porcelain"], cwd=path, capture_output=True, text=True)
            if r2.returncode == 0:
                changed_files += [line[3:].strip().strip('"') for line in r2.stdout.splitlines()
                                  if line.startswith("??") and line[3:].strip()]
        else:
            # CI mode: working tree against a base ref (branch compare)
            r = subprocess.run(["git", "diff", "--name-only", base], cwd=path, capture_output=True, text=True)
            if r.returncode == 0:
                changed_files = [f.strip() for f in r.stdout.splitlines() if f.strip()]
            else:
                r2 = subprocess.run(["git", "status", "--porcelain"], cwd=path, capture_output=True, text=True)
                if r2.returncode == 0:
                    changed_files = [line[3:].strip() for line in r2.stdout.splitlines() if line[3:].strip()]
    except Exception:
        pass
    changed_files = sorted(set(changed_files))
    schema_triggers = [f for f in changed_files if any(k in f.lower() for k in ("migration", "schema", "model", "entity", ".sql", ".prisma"))]
    api_triggers = [f for f in changed_files if any(k in f.lower() for k in ("route", "controller", "endpoint", "api"))]
    diagram_files = [f for f in changed_files if f.endswith((".graph.json", ".svg"))]
    stale = []
    covered = set()
    if getattr(args, "map", None) and os.path.exists(args.map):
        try:
            import fnmatch as _fn
            _maps = json.load(open(args.map, encoding="utf-8")).get("mappings", [])
            for _mp in _maps:
                _pat = _mp.get("code", "")
                covered.update(f for f in changed_files
                               if _fn.fnmatch(f, _pat) or _fn.fnmatch(f.replace("\\", "/"), _pat)
                               or _fn.fnmatch(os.path.basename(f), _pat))
        except (json.JSONDecodeError, OSError):
            pass
    schema_triggers = [f for f in schema_triggers if f not in covered]
    api_triggers = [f for f in api_triggers if f not in covered]
    if schema_triggers and not any("schema" in d.lower() for d in diagram_files):
        stale.append({"domain": "database", "changed_files": schema_triggers, "remediation": "py graph.py extract schema <model_file> -o docs/schema.graph.json"})
    if api_triggers and not any("route" in d.lower() or "arch" in d.lower() for d in diagram_files):
        stale.append({"domain": "architecture_api", "changed_files": api_triggers, "remediation": "py graph.py extract routes <route_file> -o docs/arch.graph.json"})
    if getattr(args, "map", None):
        # mapping-driven semantic check: extract code, diff against the spec.
        # No semantic difference => no drift (kills heuristic false positives).
        import fnmatch
        me = os.path.abspath(__file__)
        try:
            with open(args.map, encoding="utf-8") as f:
                mappings = json.load(f).get("mappings", [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            sys.exit(f"bad --map file: {e}")
        for mp in mappings:
            pat, spec_rel = mp.get("code", ""), mp.get("spec", "")
            kind = mp.get("kind", "schema")
            domain = mp.get("domain", kind)
            hits = [f for f in changed_files
                    if fnmatch.fnmatch(f, pat) or fnmatch.fnmatch(f.replace("\\", "/"), pat)
                    or fnmatch.fnmatch(os.path.basename(f), pat)]
            if not hits or spec_rel in changed_files or any(s.get("diagram_spec") == spec_rel for s in stale):
                continue
            specs = []
            for h in hits:
                src = os.path.join(path, h)
                if not os.path.exists(src):
                    continue
                r = subprocess.run([sys.executable, me, "extract", kind, src],
                                   capture_output=True, text=True)
                try:
                    specs.append(json.loads(r.stdout))
                except json.JSONDecodeError:
                    pass
            remedy = f"py graph.py extract {kind} {hits[0]} -o {spec_rel}"
            if not specs:
                stale.append({"domain": domain, "changed_files": hits, "diagram_spec": spec_rel,
                              "diff_summary": "extractor produced no spec (unverifiable)",
                              "remediation_cmd": remedy})
                continue
            spec_path = os.path.join(path, spec_rel)
            if not os.path.exists(spec_path):
                stale.append({"domain": domain, "changed_files": hits, "diagram_spec": spec_rel,
                              "diff_summary": "diagram spec missing", "remediation_cmd": remedy})
                continue
            with open(spec_path, encoding="utf-8") as f:
                diff = _spec_diff(json.load(f), _merge_specs(specs, kind), kind)
            if diff:
                stale.append({"domain": domain, "changed_files": hits, "diagram_spec": spec_rel,
                              "diff_summary": diff, "remediation_cmd": remedy})
    drift_detected = bool(stale)
    report = {
        "ok": not drift_detected,
        "drift": drift_detected,
        "changed_files_count": len(changed_files),
        "stale_domains": stale,
        "remediation_hint": "Run suggested extraction commands or update corresponding .graph.json specs before committing."
    }
    print(json.dumps(report, indent=2))
    if args.ci and drift_detected:
        raise SystemExit(1)


def do_mcp(args):
    """Minimal MCP server over stdio (newline-delimited JSON-RPC, pure stdlib).
    Render tools write files and return paths+summary (not pixels) to keep token cost low."""
    import subprocess
    me = os.path.abspath(__file__)
    _spec_props = {"spec": {"type": "string"}, "out": {"type": "string"}, "corners": {"type": "string"}}
    TOOLS = [
        {"name": "describe", "description": "Minimal schema, budgets, rules + example for a graph type. Call FIRST.",
         "inputSchema": {"type": "object", "properties": {"type": {"type": "string", "enum": sorted(DESCRIBE)}}}},
        {"name": "validate", "description": "Check a spec JSON or CSV before rendering. Returns ok/errors with fixes.",
         "inputSchema": {"type": "object", "required": ["target"],
                          "properties": {"target": {"type": "string"}, "kind": {"type": "string", "enum": ["scatter", "bar", "line"]},
                                         "x": {"type": "string"}, "y": {"type": "string"},
                                         "group": {"type": "string"}, "facet": {"type": "string"}}}},
        {"name": "infer", "description": "Propose a scatter spec from a CSV: column roles, groups, render command.",
         "inputSchema": {"type": "object", "required": ["target"], "properties": {"target": {"type": "string"}}}},
        {"name": "audit", "description": "Geometry + taste gate on a rendered .svg/.html. Call AFTER rendering.",
         "inputSchema": {"type": "object", "required": ["target"], "properties": {"target": {"type": "string"}}}},
        {"name": "scatter", "description": "Render CSV scatter. Writes OUT.html + OUT.svg + OUT.graph.json. Validate first.",
         "inputSchema": {"type": "object", "required": ["csv", "x", "y", "out"],
                          "properties": {k: {"type": "string"} for k in
                                         ("csv", "x", "y", "out", "title", "subtitle", "figure", "xlabel", "xunit",
                                          "ylabel", "yunit", "group", "yerr", "facet", "source", "caption", "corners")}}},
        {"name": "diagram", "description": "Render flow/arch/seq/schema spec JSON. Writes OUT.html + OUT.svg + receipt. Validate first.",
         "inputSchema": {"type": "object", "required": ["type", "spec", "out"],
                          "properties": {"type": {"type": "string", "enum": ["flow", "arch", "seq", "schema"]},
                                         "spec": {"type": "string"}, "out": {"type": "string"}, "corners": {"type": "string"}}}},
        {"name": "bar", "description": "Render CSV bar chart. Writes OUT.html + OUT.svg + receipt.",
         "inputSchema": {"type": "object", "required": ["csv", "out"],
                          "properties": {k: {"type": "string"} for k in
                                         ("csv", "out", "cat", "val", "title", "subtitle", "figure", "group",
                                          "orientation", "sort", "xlabel", "ylabel", "unit", "source", "caption", "corners")}}},
        {"name": "line", "description": "Render CSV line/trend chart. Writes OUT.html + OUT.svg + receipt.",
         "inputSchema": {"type": "object", "required": ["csv", "out"],
                          "properties": {k: {"type": "string"} for k in
                                         ("csv", "out", "x", "y", "title", "subtitle", "figure", "group",
                                          "xlabel", "xunit", "ylabel", "yunit", "source", "caption", "corners")}}},
        {"name": "sync", "description": "Auto-fix bot: monitor, extract, validate, recompile docs, audit, optionally commit.",
         "inputSchema": {"type": "object",
                          "properties": {"path": {"type": "string"}, "base": {"type": "string"},
                                         "map": {"type": "string"}, "docs": {"type": "string"},
                                         "commit": {"type": "string"}}}},
    ]

    def run(cmd):
        p = subprocess.run(cmd, capture_output=True, text=True)
        return p.returncode, (p.stdout or "") + (p.stderr or "")

    def call(name, a):
        a = a or {}
        if name == "describe":
            c = [sys.executable, me, "describe"] + ([a["type"]] if a.get("type") else [])
        elif name == "validate":
            c = [sys.executable, me, "validate", a["target"]] + sum(
                ([f"--{k}", a[k]] for k in ("x", "y", "group", "facet") if a.get(k)), [])
            if a.get("kind"):
                c += ["--type", a["kind"]]
        elif name == "infer":
            c = [sys.executable, me, "infer", a["target"]]
        elif name == "audit":
            c = [sys.executable, me, "audit", a["target"]]
        elif name == "scatter":
            c = [sys.executable, me, "scatter", a["csv"], "--x", a["x"], "--y", a["y"], "-o", a["out"]]
            for k in ("title", "subtitle", "figure", "xlabel", "xunit", "ylabel", "yunit",
                      "group", "yerr", "facet", "source", "caption", "corners"):
                if a.get(k):
                    c += [f"--{k}", a[k]]
        elif name == "diagram":
            c = [sys.executable, me, a["type"], a["spec"], "-o", a["out"]]
            if a.get("corners"):
                c += ["--corners", a["corners"]]
        elif name == "sync":
            c = [sys.executable, me, "sync"]
            for k in ("path", "base", "map"):
                if a.get(k):
                    c += [f"--{k}", a[k]]
            if a.get("docs"):
                c += ["--docs"] + [d.strip() for d in a["docs"].split(",") if d.strip()]
            if str(a.get("commit", "")).lower() in ("1", "true", "yes"):
                c += ["--commit"]
        elif name in ("bar", "line"):
            pos = {"bar": "csv", "line": "csv"}[name]
            c = [sys.executable, me, name, a[pos], "-o", a["out"]]
            flagmap = {"bar": ("cat", "val", "title", "subtitle", "figure", "group", "orientation",
                               "sort", "xlabel", "ylabel", "unit", "source", "caption", "corners"),
                       "line": ("x", "y", "title", "subtitle", "figure", "group", "xlabel", "xunit",
                                "ylabel", "yunit", "source", "caption", "corners")}[name]
            for k in flagmap:
                if a.get(k):
                    c += [f"--{k}", a[k]]
        else:
            return {"isError": True, "content": [{"type": "text", "text": f"unknown tool {name}"}]}
        rc, out = run(c)
        return {"content": [{"type": "text", "text": out[:12000]}], ** ({"isError": True} if rc else {})}

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid, method, params = m.get("id"), m.get("method"), m.get("params", {}) or {}
        if method == "initialize":
            res = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                   "serverInfo": {"name": "graph", "version": "0.3.0"}}
        elif method in ("notifications/initialized",):
            continue
        elif method == "tools/list":
            res = {"tools": TOOLS}
        elif method == "tools/call":
            res = call(params.get("name"), params.get("arguments"))
        else:
            res = {"error": {"code": -32601, "message": f"no {method}"}}
        if "error" in (res if isinstance(res, dict) else {}):
            e = res["error"]
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "error": e}) + "\n")
        else:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": res}) + "\n")
        sys.stdout.flush()


def _cli_theme(args):
    return get_theme(getattr(args, "theme", None) or "editorial", getattr(args, "theme_file", None))


def _cli_notes(args, kind):
    texts = getattr(args, "note", None) or []
    ats = getattr(args, "note_at", None) or []
    out = []
    for i, text in enumerate(texts):
        if i >= len(ats):
            break
        at = ats[i]
        if kind == "scatter":
            bits = [b.strip() for b in str(at).split(",")]
            if len(bits) == 2:
                out.append({"x": bits[0], "y": bits[1], "text": text})
        else:
            out.append({"at": at, "text": text})
    return out or None


def _chart_flags(p):
    p.add_argument("--grid", dest="grid", action="store_true", help="draw gridlines (default)")
    p.add_argument("--no-grid", dest="grid", action="store_false", help="drop gridlines; keep ticks")
    p.add_argument("--markers", dest="markers", action="store_true", help="point dots or bar value labels (default)")
    p.add_argument("--no-markers", dest="markers", action="store_false", help="hide point dots or bar value labels")
    p.add_argument("--highlight", action="append", default=[],
                   help="category, x value, group, or place drawn in accent (repeatable)")
    p.set_defaults(grid=True, markers=True)


def main():
    ap = argparse.ArgumentParser(prog="graph")
    sub = ap.add_subparsers(dest="cmd", required=True)
    _render_parsers = {}
    for name in ("flow", "arch", "seq", "schema"):
        p = sub.add_parser(name); p.add_argument("spec"); p.add_argument("-o", required=True)
        p.add_argument("--corners", default="editorial", choices=["sharp", "rounded", "editorial"])
        p.add_argument("--theme", default="editorial", choices=sorted(THEMES))
        p.add_argument("--theme-file", default=None, help="JSON with theme key overrides")
        _render_parsers[name] = p
    _render_parsers["flow"].add_argument("--auto", action="store_true",
                                         help="force longest-path layering (default when no ranks given)")
    p = sub.add_parser("bar"); p.add_argument("csv"); p.add_argument("--cat", default=None)
    p.add_argument("--val", default=None); p.add_argument("--title", default="Bar Chart")
    p.add_argument("--subtitle", default=""); p.add_argument("--figure", default="Fig. 1")
    p.add_argument("--group", default=None); p.add_argument("--orientation", default="v", choices=["v", "h"])
    p.add_argument("--sort", default="none", choices=["none", "asc", "desc"])
    p.add_argument("--xlabel", default=None); p.add_argument("--ylabel", default=None)
    p.add_argument("--unit", default=""); p.add_argument("--source", default="")
    p.add_argument("--caption", default="Categorical comparison.")
    p.add_argument("--corners", default="editorial", choices=["sharp", "rounded", "editorial"])
    p.add_argument("--theme", default="editorial", choices=sorted(THEMES))
    p.add_argument("--theme-file", default=None)
    p.add_argument("--note", action="append", default=[], help="callout text (pairs with --note-at)")
    p.add_argument("--note-at", action="append", default=[], help="callout anchor: category value")
    p.add_argument("-o", required=True)
    _chart_flags(p)
    p = sub.add_parser("line"); p.add_argument("csv"); p.add_argument("--x", default=None)
    p.add_argument("--y", default=None); p.add_argument("--title", default="Line Trend")
    p.add_argument("--subtitle", default=""); p.add_argument("--figure", default="Fig. 1")
    p.add_argument("--group", default=None); p.add_argument("--xlabel", default=None)
    p.add_argument("--xunit", default=""); p.add_argument("--ylabel", default=None)
    p.add_argument("--yunit", default=""); p.add_argument("--source", default="")
    p.add_argument("--caption", default="Trend over time or continuous variable.")
    p.add_argument("--corners", default="editorial", choices=["sharp", "rounded", "editorial"])
    p.add_argument("--theme", default="editorial", choices=sorted(THEMES))
    p.add_argument("--theme-file", default=None)
    p.add_argument("--note", action="append", default=[])
    p.add_argument("--note-at", action="append", default=[], help="callout anchor: x value")
    p.add_argument("-o", required=True)
    _chart_flags(p)
    p = sub.add_parser("geo", help="point map from CSV lat/lon, or GeoJSON points and polygons")
    p.add_argument("src"); p.add_argument("--lat", default=None); p.add_argument("--lon", default=None)
    p.add_argument("--label", default=None); p.add_argument("--val", default=None)
    p.add_argument("--title", default="Map"); p.add_argument("--subtitle", default="")
    p.add_argument("--figure", default="Fig. 1"); p.add_argument("--source", default="")
    p.add_argument("--caption", default="Locations. Dot size follows the value column when one is set.")
    p.add_argument("--theme", default="editorial", choices=sorted(THEMES))
    p.add_argument("--theme-file", default=None)
    p.add_argument("-o", required=True)
    _chart_flags(p)
    p = sub.add_parser("doc", help="compile graph specs in markdown docs to standalone SVGs")
    p.add_argument("target", help="markdown file path")
    p.add_argument("--out-dir", default=None, help="assets output directory")
    p.add_argument("--check", action="store_true", help="CI check mode: verify all specs are valid")
    p = sub.add_parser("monitor", help="detect architectural drift between code and diagrams")
    p.add_argument("--path", default=".", help="project root path")
    p.add_argument("--base", default="HEAD", help="git base ref: HEAD = working tree (local), else branch compare (CI)")
    p.add_argument("--ci", action="store_true", help="fail exit code on drift")
    p.add_argument("--map", default=None, help="mappings JSON: code globs -> spec files for semantic drift compare")
    p = sub.add_parser("sync", help="auto-fix bot: monitor -> extract -> validate -> doc -> audit (-> commit)")
    p.add_argument("--path", default=".", help="project root path")
    p.add_argument("--base", default="HEAD", help="git base ref: HEAD = working tree (local), else branch compare (CI)")
    p.add_argument("--map", default=None, help="mappings JSON (machine remediation needs this)")
    p.add_argument("--docs", nargs="*", default=[], help="markdown docs to recompile after sync")
    p.add_argument("--commit", action="store_true", help="create a local commit (never pushes)")
    p = sub.add_parser("extract", help="reverse-extract diagram specs from code (AST/DDL)")
    sub_ext = p.add_subparsers(dest="ext_type", required=True)
    p_sc = sub_ext.add_parser("schema", help="extract ER schema from SQL DDL or Python ORM models")
    p_sc.add_argument("source", help="source file (.sql, .py, .prisma)")
    p_sc.add_argument("-o", default=None, help="output .json spec file")
    p_rt = sub_ext.add_parser("routes", help="extract service/API routes from FastAPI/Flask code")
    p_rt.add_argument("source", help="source file (.py, .ts, .json)")
    p_rt.add_argument("-o", default=None, help="output .json spec file")
    p = sub.add_parser("scatter"); p.add_argument("csv"); p.add_argument("--x", default=None)
    p.add_argument("--y", default=None); p.add_argument("--title", default="Scatter")
    p.add_argument("--subtitle", default=""); p.add_argument("--figure", default="Fig. 1")
    p.add_argument("--xlabel", default=None); p.add_argument("--xunit", default="")
    p.add_argument("--ylabel", default=None); p.add_argument("--yunit", default="")
    p.add_argument("--group", default=None); p.add_argument("--yerr", default=None)
    p.add_argument("--facet", default=None); p.add_argument("--source", default="")
    p.add_argument("--caption", default="Relationship between the two variables. Points show individual observations.")
    p.add_argument("--corners", default="editorial", choices=["sharp", "rounded", "editorial"])
    p.add_argument("--theme", default="editorial", choices=sorted(THEMES))
    p.add_argument("--theme-file", default=None)
    p.add_argument("--note", action="append", default=[])
    p.add_argument("--note-at", action="append", default=[], help="callout anchor: x,y")
    p.add_argument("-o", required=True)
    _chart_flags(p)
    p = sub.add_parser("export", help="render receipt to png/pdf/svg in a layout")
    p.add_argument("target", help="base path, .html or .svg (receipt .graph.json must sit beside it)")
    p.add_argument("--to", default="png", choices=["png", "pdf", "svg"])
    p.add_argument("--layout", default="figure", choices=sorted(LAYOUTS))
    p.add_argument("--width", type=int, default=1600, help="raster width px (png)")
    p.add_argument("--theme", default=None, choices=sorted(THEMES), help="override receipt theme")
    p.add_argument("--theme-file", default=None)
    p.add_argument("-o", default=None)
    p = sub.add_parser("describe", help="minimal schema+rules+example per type (agent context)")
    p.add_argument("type", nargs="?", default=None, choices=sorted(DESCRIBE))
    p = sub.add_parser("validate", help="check spec/csv BEFORE render; JSON report, exit 1 on error")
    p.add_argument("target"); p.add_argument("--x", default=None); p.add_argument("--y", default=None)
    p.add_argument("--group", default=None); p.add_argument("--facet", default=None)
    p.add_argument("--type", default="scatter", choices=["scatter", "bar", "line", "geo"],
                   help="csv shape to validate against (default: scatter). geo: --x lon, --y lat")
    p = sub.add_parser("infer", help="propose a scatter spec from a CSV (agent starting point)")
    p.add_argument("target")
    p = sub.add_parser("audit", help="check rendered svg/html AFTER render; geometry+taste gate as JSON")
    p.add_argument("target")
    p = sub.add_parser("mcp", help="MCP server over stdio (describe/validate/infer/audit/scatter/diagram/bar/line)")
    a = ap.parse_args()
    if a.cmd == "mcp":
        do_mcp(a)
        return
    if a.cmd == "export":
        do_export(a)
        return
    if a.cmd == "describe":
        do_describe(a)
        return
    if a.cmd == "validate":
        do_validate(a)
        return
    if a.cmd == "infer":
        do_infer(a)
        return
    if a.cmd == "audit":
        do_audit(a)
        return
    if a.cmd == "doc":
        do_doc(a)
        return
    if a.cmd == "monitor":
        do_monitor(a)
        return
    if a.cmd == "sync":
        do_sync(a)
        return
    if a.cmd == "extract":
        do_extract(a)
        return
    if a.cmd in ("flow", "arch", "seq", "schema"):
        spec = load_spec(a.spec)
        theme = _cli_theme(a)
        if a.cmd == "flow":
            svg, _, _ = render_flow(spec, a.corners, getattr(a, "auto", False), theme)
            item_cnt = len(spec.get("nodes", []))
        elif a.cmd == "arch":
            svg, _, _ = render_arch(spec, a.corners, theme)
            item_cnt = len(spec.get("nodes", []))
        elif a.cmd == "seq":
            svg, _, _ = render_seq(spec, a.corners, theme)
            item_cnt = len(spec.get("actors", []))
        elif a.cmd == "schema":
            svg, _, _ = render_schema(spec, a.corners, theme)
            item_cnt = len(spec.get("tables", []))
        o, s = write_out(svg, a.cmd, spec.get("title", a.cmd), spec.get("sub", ""),
                         f"{a.cmd} · {os.path.basename(a.spec)}", a.o,
                         caption=spec.get("sub", ""), cap_title=spec.get("title", a.cmd) + ".",
                         source="Self-contained HTML + SVG.", corners=a.corners, theme=theme)
        save_receipt(o, {"cmd": a.cmd, "spec": a.spec, "corners": a.corners, "theme": theme.get("_name")})
        print(f"wrote {o} + {s} + {os.path.splitext(o)[0]}.graph.json ({item_cnt} items)")
    elif a.cmd == "bar":
        theme = _cli_theme(a)
        notes = _cli_notes(a, "bar")
        svg, _, _, n = render_bar(a.csv, a.cat, a.val, a.title, a.subtitle, a.figure,
                                  a.group, a.orientation, a.sort, a.xlabel, a.ylabel,
                                  a.unit, a.source, a.corners, chrome=True, theme=theme, notes=notes,
                                  grid=a.grid, markers=a.markers, highlights=a.highlight)
        o, s = write_out(svg, "bar", a.title, a.subtitle or f"{n} items · {os.path.basename(a.csv)}",
                         f"{a.figure} · bar · {os.path.basename(a.csv)}", a.o,
                         caption=a.caption, cap_title=a.title + ".",
                         source=(a.source or os.path.basename(a.csv)), corners=a.corners, theme=theme)
        save_receipt(o, {"cmd": "bar", "csv": a.csv, "cat": a.cat, "val": a.val, "title": a.title,
                         "subtitle": a.subtitle, "figure": a.figure, "group": a.group,
                         "orientation": a.orientation, "sort": a.sort, "unit": a.unit,
                         "xlabel": a.xlabel, "ylabel": a.ylabel,
                         "source": a.source, "corners": a.corners, "theme": theme.get("_name"),
                         "grid": a.grid, "markers": a.markers, "highlights": a.highlight})
        print(f"wrote {o} + {s} + {os.path.splitext(o)[0]}.graph.json ({n} bars)")
    elif a.cmd == "line":
        theme = _cli_theme(a)
        notes = _cli_notes(a, "line")
        svg, _, _, n = render_line(a.csv, a.x, a.y, a.title, a.subtitle, a.figure,
                                   a.group, a.xlabel, a.xunit, a.ylabel, a.yunit,
                                   a.source, a.corners, chrome=True, theme=theme, notes=notes,
                                   grid=a.grid, markers=a.markers, highlights=a.highlight)
        o, s = write_out(svg, "line", a.title, a.subtitle or f"{n} points · {os.path.basename(a.csv)}",
                         f"{a.figure} · line · {os.path.basename(a.csv)}", a.o,
                         caption=a.caption, cap_title=a.title + ".",
                         source=(a.source or os.path.basename(a.csv)), corners=a.corners, theme=theme)
        save_receipt(o, {"cmd": "line", "csv": a.csv, "x": a.x, "y": a.y, "title": a.title,
                         "subtitle": a.subtitle, "figure": a.figure, "group": a.group,
                         "source": a.source, "corners": a.corners, "theme": theme.get("_name"),
                         "grid": a.grid, "markers": a.markers, "highlights": a.highlight})
        print(f"wrote {o} + {s} + {os.path.splitext(o)[0]}.graph.json ({n} points)")
    elif a.cmd == "geo":
        theme = _cli_theme(a)
        svg, _, _, n = render_geo(a.src, a.lat, a.lon, a.label, a.val, a.title, a.subtitle,
                                  a.figure, a.source, theme, chrome=True,
                                  grid=a.grid, markers=a.markers, highlights=a.highlight)
        o, s = write_out(svg, "geo", a.title, a.subtitle or f"{n} places · {os.path.basename(a.src)}",
                         f"{a.figure} · geo · {os.path.basename(a.src)}", a.o,
                         caption=a.caption, cap_title=a.title + ".",
                         source=(a.source or os.path.basename(a.src)), theme=theme)
        save_receipt(o, {"cmd": "geo", "src": a.src, "lat": a.lat, "lon": a.lon, "label": a.label,
                         "val": a.val, "title": a.title, "subtitle": a.subtitle, "figure": a.figure,
                         "source": a.source, "theme": theme.get("_name"),
                         "grid": a.grid, "markers": a.markers, "highlights": a.highlight})
        print(f"wrote {o} + {s} + {os.path.splitext(o)[0]}.graph.json ({n} places)")
    else:
        theme = _cli_theme(a)
        kw = dict(xcol=a.x, ycol=a.y, title=a.title, subtitle=a.subtitle, figure=a.figure,
                  xlabel=a.xlabel or a.x or "", xunit=a.xunit, ylabel=a.ylabel or a.y or "",
                  yunit=a.yunit, groupcol=a.group, yerrcol=a.yerr, facetcol=a.facet,
                  source=a.source, corners=a.corners, theme=theme, notes=_cli_notes(a, "scatter"),
                  grid=a.grid, markers=a.markers, highlights=a.highlight)
        svg, _, _, n = render_scatter(a.csv, chrome=True, **kw)
        o, s = write_out(svg, "scatter", a.title,
                         a.subtitle or f"{n} points · {os.path.basename(a.csv)}",
                         f"{a.figure} · scatter · {os.path.basename(a.csv)}", a.o,
                         caption=a.caption, cap_title=a.title + ".",
                         source=(a.source or os.path.basename(a.csv)),
                         corners=a.corners, theme=theme)
        save_receipt(o, {"cmd": "scatter", "csv": a.csv, "x": a.x, "y": a.y, "title": a.title,
                         "subtitle": a.subtitle, "figure": a.figure,
                         "xlabel": a.xlabel or a.x or "", "xunit": a.xunit,
                         "ylabel": a.ylabel or a.y or "", "yunit": a.yunit,
                         "group": a.group, "yerr": a.yerr, "facet": a.facet,
                         "source": a.source, "corners": a.corners, "theme": theme.get("_name"),
                         "grid": a.grid, "markers": a.markers, "highlights": a.highlight})
        print(f"wrote {o} + {s} + {os.path.splitext(o)[0]}.graph.json ({n} points)")


if __name__ == "__main__":
    main()
