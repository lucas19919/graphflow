#!/usr/bin/env python3
"""graph — lightweight stunning graphs. Pure stdlib. No deps.
Usage:
  python graph.py flow examples/flow_decision.yaml -o out/flow.html
  python graph.py arch examples/arch.yaml -o out/arch.html
  python graph.py scatter examples/scatter.csv --x dose --y expr -o out/scatter.html
Outputs self-contained .html (hero) + .svg sidecar.
"""
import argparse, csv, html, json, os, sys

__version__ = "0.5.0"

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


# ---------- Mermaid input ----------
# Agents already write Mermaid. These read flowchart/graph, sequenceDiagram, and erDiagram text
# into the same specs the JSON route uses, so layout, audit, and repair apply unchanged.

_MM_KINDS = {"flowchart": "flow", "graph": "flow", "sequencediagram": "seq", "erdiagram": "schema"}


def _mermaid_lines(text):
    """(title, [(line number, stripped line)]): front matter title pulled out, comments dropped."""
    raw = str(text).replace("\r\n", "\n").split("\n")
    title, start = "", 0
    if raw and raw[0].strip() == "---":
        for j in range(1, len(raw)):
            if raw[j].strip() == "---":
                for fm in raw[1:j]:
                    if fm.strip().lower().startswith("title:"):
                        title = fm.split(":", 1)[1].strip().strip("\"'")
                start = j + 1
                break
    out = []
    for k in range(start, len(raw)):
        s = raw[k].strip()
        if s and not s.startswith("%%"):
            out.append((k + 1, s))
    return title, out


def _mermaid_kind(text):
    """'flow', 'seq', or 'schema' for Mermaid text we read; the Mermaid keyword for one we do not;
    None when the text is not Mermaid at all."""
    _, lines = _mermaid_lines(text)
    if not lines:
        return None
    head = lines[0][1].split()[0].lower().rstrip(":;")
    if head in _MM_KINDS:
        return _MM_KINDS[head]
    known = ("pie", "classdiagram", "statediagram", "statediagram-v2", "gantt", "journey", "gitgraph",
             "mindmap", "timeline", "quadrantchart", "xychart-beta", "sankey-beta", "block-beta",
             "architecture-beta", "requirementdiagram", "c4context", "kanban", "packet-beta", "radar-beta")
    return head if head in known else None


def _mm_text(s):
    """A Mermaid label as plain text: quotes, <br>, markdown marks, and entity codes removed."""
    import re
    s = str(s or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'`":
        s = s[1:-1]
    s = re.sub(r"<br\s*/?>|\\n", " ", s, flags=re.I)
    s = s.replace("**", "").replace("`", "").replace("#quot;", '"').replace("#amp;", "&")
    return " ".join(s.split())


# (open, close, shape, tag); longer openers first so "([" is not read as "("
_MM_SHAPES = [("(((", ")))", "oval", ""), ("([", "])", "oval", ""), ("((", "))", "oval", ""),
              ("[(", ")]", "rect", "DB"), ("[[", "]]", "rect", ""), ("{{", "}}", "rect", ""),
              ("[/", "/]", "rect", ""), ("[\\", "\\]", "rect", ""), ("[/", "\\]", "rect", ""),
              ("[\\", "/]", "rect", ""), ("[", "]", "rect", ""), ("(", ")", "rect", ""),
              ("{", "}", "diamond", ""), (">", "]", "rect", "")]


def _mm_flow(lines, title):
    import re
    nodes, order, edges, groups, stack = {}, [], [], {}, []
    errors, warnings = [], []
    id_re = re.compile(r"[^\W][\w.]*", re.U)
    simple = re.compile(r"(<)?(-{2,}>|-{3,}|-\.+->|-\.+-|={2,}>|={3,}|-{2,}[xo]|~~~)(?:\|([^|]*)\|)?")
    texty = re.compile(r"(--|-\.|==)\s+(.+?)\s+(-{2,}>|-{3,}|\.-+>|\.-+|={2,}>|={3,}|-{2,}[xo])")

    def node_at(s, i, ln):
        m = id_re.match(s, i)
        if not m:
            return None, i
        nid, i = m.group(0), m.end()
        name, shape, tag = None, None, ""
        for op, cl, sh, tg in _MM_SHAPES:
            if s.startswith(op, i):
                j = i + len(op)
                if j < len(s) and s[j] == '"':
                    q = s.find('"', j + 1)
                    k = s.find(cl, q + 1) if q >= 0 else -1
                else:
                    k = s.find(cl, j)
                if k < 0:
                    errors.append({"msg": f"line {ln}: '{op}' opened after '{nid}' is never closed", "fix": f"close it with '{cl}'"})
                    return None, len(s)
                name, shape, tag, i = _mm_text(s[j:k]), sh, tg, k + len(cl)
                break
        focal = False
        cm = re.match(r":::([\w-]+)", s[i:])
        if cm:
            focal = cm.group(1).lower() in ("focal", "accent", "highlight", "primary")
            i += cm.end()
        if nid not in nodes:
            nodes[nid] = {"id": nid, "name": nid}
            order.append(nid)
        n = nodes[nid]
        if name is not None:
            fa = re.search(r"fa[srb]?:fa-([\w-]+)", name)
            if fa:
                name = _mm_text(name.replace(fa.group(0), ""))
                if _FA_ICONS.get(fa.group(1)):
                    n["icon"] = _FA_ICONS[fa.group(1)]
            n["name"] = name or nid
        if shape and shape != "rect":
            n["shape"] = shape
        if tag:
            n["tag"] = tag
        if focal:
            n["focal"] = True
        if stack and "group" not in n:
            n["group"] = stack[-1]
        return nid, i

    def group_at(s, i, ln):
        ids = []
        while True:
            while i < len(s) and s[i] == " ":
                i += 1
            nid, i = node_at(s, i, ln)
            if nid is None:
                return ids, i
            ids.append(nid)
            m = re.match(r"\s*&\s*", s[i:])
            if not m:
                return ids, i
            i += m.end()

    for ln, line in lines[1:]:
        low = line.lower()
        if low.startswith("subgraph"):
            rest = line[8:].strip()
            m = re.match(r'([^\s\["]+)\s*\[\s*(.*?)\s*\]$', rest)
            gid, name = (m.group(1), _mm_text(m.group(2))) if m else (_mm_text(rest) or f"group{len(groups) + 1}", _mm_text(rest))
            gid = gid if re.fullmatch(r"[\w.-]+", gid) else re.sub(r"\W+", "_", gid).strip("_") or f"group{len(groups) + 1}"
            if stack:
                warnings.append({"msg": f"line {ln}: nested subgraph '{name}' is drawn beside its parent, not inside it",
                                 "fix": "flatten the nesting if the frame matters"})
            groups.setdefault(gid, {"id": gid, "name": name or gid})
            stack.append(gid)
            continue
        if low == "end":
            if stack:
                stack.pop()
            continue
        if re.match(r"(classdef|class|style|linkstyle|click|direction|acctitle|accdescr)\b", low):
            continue
        for stmt in [p.strip() for p in line.split(";") if p.strip()]:
            before = len(errors)
            prev, i = group_at(stmt, 0, ln)
            if not prev:
                if len(errors) > before:
                    continue
                errors.append({"msg": f"line {ln}: cannot read '{stmt[:40]}'",
                               "fix": "write 'A[Label] --> B{Question?}' style lines"})
                continue
            while True:
                rest = stmt[i:].lstrip()
                if not rest:
                    break
                off = len(stmt) - len(rest)
                m = simple.match(rest)
                label, arrow = "", None
                if m:
                    arrow, label = m.group(2), _mm_text(m.group(3) or "")
                else:
                    m = texty.match(rest)
                    if m:
                        arrow, label = m.group(1) + m.group(3), _mm_text(m.group(2))
                if not m:
                    errors.append({"msg": f"line {ln}: cannot read '{rest[:30]}' after '{prev[-1]}'",
                                   "fix": "join nodes with -->, ---, -.->, or ==>; labels go in -->|label|"})
                    break
                nxt, i = group_at(stmt, off + m.end(), ln)
                if not nxt:
                    errors.append({"msg": f"line {ln}: arrow from '{prev[-1]}' has no target", "fix": "add the node after the arrow"})
                    break
                for a in prev:
                    for b in nxt:
                        e = {"from": a, "to": b}
                        if label:
                            e["label"] = label
                        if "." in arrow:
                            e["async"] = True
                        if "=" in arrow:
                            e["focal"] = True
                        edges.append(e)
                prev = nxt
    # An arrow to a subgraph's id lands on that group's first member, not on a stray box.
    firsts = {}
    for nid in order:
        g = nodes[nid].get("group")
        if g and g not in firsts:
            firsts[g] = nid
    for gid in groups:
        if gid in nodes and gid in firsts and nodes[gid].get("name") == gid and not nodes[gid].get("group"):
            for e in edges:
                for k in ("from", "to"):
                    if e[k] == gid:
                        e[k] = firsts[gid]
            order.remove(gid)
            del nodes[gid]
    spec = {"title": title, "nodes": [nodes[n] for n in order], "edges": edges,
            "groups": [g for g in groups.values()]}
    if len(spec["nodes"]) > 9 or len(edges) > 12:
        spec["budget"] = False
        warnings.append({"msg": f"{len(spec['nodes'])} nodes and {len(edges)} arrows: over the 9 and 12 that read at a glance",
                         "fix": "split it into an overview and a detail view if it reads slowly"})
    return spec, errors, warnings


def _mm_seq(lines, title):
    import re
    actors, aid, messages, errors, warnings = [], {}, [], [], []
    msg = re.compile(r"^(.+?)\s*(-->>|->>|--\)|-\)|--x|-x|-->|->)\s*([+-])?\s*(.+?)\s*:\s*(.*)$")

    def actor(name, label=None, kind=None):
        name = name.strip()
        if name not in aid:
            aid[name] = len(actors)
            actors.append({"id": name, "name": _mm_text(label) if label else name})
        elif label:
            actors[aid[name]]["name"] = _mm_text(label)
        if kind == "actor":
            actors[aid[name]]["tag"] = "USER"
    skipped = 0
    for ln, line in lines[1:]:
        low = line.lower()
        m = re.match(r"^(participant|actor)\s+(.+?)(?:\s+as\s+(.+))?$", line, re.I)
        if m:
            actor(m.group(2), m.group(3), m.group(1).lower())
            continue
        if low.startswith("title"):
            title = line[5:].strip(" :")
            continue
        m = msg.match(line)
        if m:
            a, arrow, _, b, text = m.groups()
            actor(a)
            actor(b)
            item = {"from": a.strip(), "to": b.strip(), "label": _mm_text(text)}
            if arrow in ("-->>", "-->", "--x"):
                item["reply"] = True
            if ")" in arrow:
                item["async"] = True
            messages.append(item)
            continue
        if re.match(r"(note|loop|alt|else|opt|par|and|critical|option|break|rect|end|activate|deactivate|"
                    r"autonumber|box|create|destroy|links?|properties|details)\b", low):
            skipped += 1
            continue
        errors.append({"msg": f"line {ln}: cannot read '{line[:40]}'", "fix": "write 'A->>B: message' lines"})
    if skipped:
        warnings.append({"msg": f"{skipped} notes, blocks, or activations are not drawn",
                         "fix": "put what matters in the message labels"})
    spec = {"title": title, "actors": actors, "messages": messages}
    if len(actors) > 6 or len(messages) > 16:
        spec["budget"] = False
        warnings.append({"msg": f"{len(actors)} actors and {len(messages)} messages: over the 6 and 16 that read at a glance",
                         "fix": "split it into sub-sequences if it reads slowly"})
    return spec, errors, warnings


def _mm_er(lines, title):
    import re
    tables, order, rels, errors, warnings = {}, [], [], [], []
    rel = re.compile(r"^([\w-]+)\s*(\|o|\|\||\}o|\}\|)(--|\.\.)(o\||\|\||o\{|\|\{)\s*([\w-]+)\s*:\s*(.*)$")

    def table(name):
        if name not in tables:
            tables[name] = {"id": name, "name": name, "columns": []}
            order.append(name)
        return tables[name]
    cur = None
    for ln, line in lines[1:]:
        if cur is not None:
            if line.startswith("}"):
                cur = None
                continue
            parts = line.split()
            if len(parts) >= 2:
                keys = " ".join(parts[2:]).upper()
                col = {"name": parts[1], "type": parts[0]}
                if "PK" in keys:
                    col["pk"] = True
                if "FK" in keys:
                    col["fk"] = True
                if "UK" in keys:
                    col["unique"] = True
                cur["columns"].append(col)
            continue
        m = re.match(r"^([\w-]+)\s*\{\s*$", line)
        if m:
            cur = table(m.group(1))
            continue
        m = rel.match(line)
        if m:
            a, left, _, right, b, verb = m.groups()
            table(a)
            table(b)
            many_l, many_r = "}" in left, "{" in right
            card = {(False, True): "1:N", (True, False): "N:1", (True, True): "M:N"}.get((many_l, many_r), "1:1")
            verb = _mm_text(verb)
            rels.append({"from": a, "to": b, "label": f"{card} {verb}".strip()})
            continue
        if re.match(r"^[\w-]+$", line):
            table(line)
            continue
        errors.append({"msg": f"line {ln}: cannot read '{line[:40]}'", "fix": "write 'A ||--o{ B : label' or 'A { type name PK }'"})
    spec = {"title": title, "tables": [tables[n] for n in order], "relations": rels}
    if len(order) > 6:
        spec["budget"] = False
        warnings.append({"msg": f"{len(order)} tables: over the 6 that read at a glance", "fix": "split by bounded context"})
    return spec, errors, warnings


def _mermaid_spec(text):
    """Mermaid text as a spec dict. Parse problems ride along in _errors and _warnings."""
    title, lines = _mermaid_lines(text)
    kind = _mermaid_kind(text)
    if kind not in ("flow", "seq", "schema"):
        name = lines[0][1].split()[0] if lines else "(empty)"
        return {"_kind": None, "_errors": [{"msg": f"Mermaid '{name}' is not read yet",
                                             "fix": "flowchart, graph, sequenceDiagram, and erDiagram are; or use describe for a JSON type"}]}
    if kind == "flow":
        head = lines[0][1].split()
        if len(head) > 1 and head[1].upper() in ("LR", "RL", "BT"):
            pre = [{"msg": f"direction {head[1].upper()} is drawn top-down", "fix": "this engine lays flows out top to bottom"}]
        else:
            pre = []
        spec, errors, warnings = _mm_flow(lines, title)
        warnings = pre + warnings
    elif kind == "seq":
        spec, errors, warnings = _mm_seq(lines, title)
    else:
        spec, errors, warnings = _mm_er(lines, title)
    spec["_kind"] = kind
    main = {"flow": "nodes", "seq": "messages", "schema": "tables"}[kind]
    if not errors and not spec.get(main):
        errors = [{"msg": f"this {lines[0][1].split()[0]} has no {'messages' if kind == 'seq' else main} yet",
                   "fix": {"flow": "add a line like 'A[Start] --> B[Next]'", "seq": "add a line like 'A->>B: hello'",
                           "schema": "add a line like 'A ||--o{ B : has'"}[kind]}]
    if errors:
        spec["_errors"] = errors
    if warnings:
        spec["_warnings"] = warnings
    return spec


def load_spec(path):
    with open(path, encoding="utf-8") as f:
        txt = f.read()
    if path.lower().endswith((".mmd", ".mermaid")) or _mermaid_kind(txt):
        return _mermaid_spec(txt)
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
        return sh, 80.0, float(node.get("_h", 64)) / 2.0
    return "box", 80.0, float((node or {}).get("_h", BOX_H)) / 2.0


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


def assign_ports(pos, edges, layered=False, fixed=None, trunk=False):
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
        if fixed and i in fixed:
            s1, s2 = fixed[i]
        elif layered and abs(y2 - y1) > 1:
            # between rows: out the bottom, sideways in the gap, in the top. Never along a row.
            s1, s2 = ("s", "n") if y2 > y1 else ("n", "s")
        else:
            s1 = node_side(x1, y1, n1, x2, y2)
            s2 = node_side(x2, y2, n2, x1, y1)
        sides.append((s1, s2))
        # port_on slides along the side's tangent, which runs right-to-left on "s" and
        # bottom-to-top on "w". Flip the key there, so the leftmost target gets the leftmost port.
        k_out = (y2 if s1 in ("e", "w") else x2) * (-1 if s1 in ("s", "w") else 1)
        k_in = (y1 if s2 in ("e", "w") else x1) * (-1 if s2 in ("s", "w") else 1)
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
        if trunk and sh == "box" and side in ("n", "s") and len(items) >= 2 and len({it[1] for it in items}) == 1:
            for ei, role, _ in items:  # one port: the arrows split (or merge) in the gap, like a tree
                along[(ei, role)] = 0.0
            continue
        if layered and len(items) == 1 and side in ("n", "s") and lim >= 8:
            # A lone port leans toward the far end of its arrow, so an exit and an entry
            # stacked in one column never land on the same x and read as one line.
            ei, role, _ = items[0]
            other = edges[ei]["to"] if role == "out" else edges[ei]["from"]
            dx = pos[other][0] - pos[nid][0]
            lean = 0.0 if abs(dx) < 1 else (12.0 if dx > 0 else -12.0)
            along[(ei, role)] = -lean if side == "s" else lean
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


def route_edge(x1, y1, side1, x2, y2, side2, r=8, stub=16, nudge=0, track=0):
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
        if side1 == side2 and abs(ay - by) >= 0.5:
            # both ends on the same side (a loop going back): run outside both boxes, not between them
            mx = min(ax, bx) if side1 == "w" else max(ax, bx)
            pts += [(mx, ay), (mx, by)]
        elif abs(ay - by) >= 0.5:
            lo, hi = sorted((ax, bx))
            mx = min(max((ax + bx) / 2.0 + nudge, lo + 8), hi - 8)
            pts += [(mx, ay), (mx, by)]
        pts.append((bx, by))
    elif (not leave_h) and (not enter_h):
        if abs(ax - bx) >= 0.5:
            my = (ay + by) / 2.0 + track  # track: its own height in a shared gap
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
    route_edge.last_pts = pts
    return _round_poly(pts, r), mx, my, vert


def edge_ends(pos, src_id, dst_id):
    x1, y1, n1 = pos[src_id]
    x2, y2, n2 = pos[dst_id]
    px, py, s1 = node_port(x1, y1, n1, x2, y2)
    qx, qy, s2 = node_port(x2, y2, n2, x1, y1)
    return px, py, s1, qx, qy, s2


def corner_rx(corners):
    return {"sharp": 0, "rounded": 10, "editorial": 6}.get(corners, 6)


def _groups_of(spec, ids):
    """Groups from spec["groups"] ({id, name, nodes}) and from each node's "group" field."""
    out, seen = [], {}
    for g in spec.get("groups") or []:
        if isinstance(g, dict) and g.get("id") is not None:
            seen[g["id"]] = {"id": g["id"], "name": g.get("name", g["id"]), "tag": g.get("tag", ""),
                             "members": [m for m in g.get("nodes") or [] if m in ids]}
            out.append(seen[g["id"]])
    for n in spec.get("nodes") or []:
        gid = n.get("group") if isinstance(n, dict) else None
        if gid is None:
            continue
        if gid not in seen:
            seen[gid] = {"id": gid, "name": str(gid), "tag": "", "members": []}
            out.append(seen[gid])
        if n.get("id") in ids and n["id"] not in seen[gid]["members"]:
            seen[gid]["members"].append(n["id"])
    return [g for g in out if g["members"]]


GROUP_PAD, GROUP_HEAD = 16, 24


def _group_columns(layers, groups, gof, edges=()):
    """Columns for a layered view with groups. Each group owns a band of columns in the rows it
    spans and its members stack inside it; other nodes take free columns outside every band that
    covers their row. Returns {node id: column} (a column may be fractional, to center a short row)."""
    keys = sorted(layers)
    rows = [layers[k] for k in keys]
    bands = []
    for k in range(len(groups)):
        hit = [r for r, row in enumerate(rows) if any(gof.get(n["id"]) == k for n in row)]
        if not hit:
            continue
        width = max(sum(1 for n in rows[r] if gof.get(n["id"]) == k) for r in hit)
        first = max(next(i for i, n in enumerate(rows[r]) if gof.get(n["id"]) == k) for r in hit)
        mean = sum(next(i for i, n in enumerate(rows[r]) if gof.get(n["id"]) == k) / max(1, len(rows[r])) for r in hit) / len(hit)
        bands.append({"k": k, "lo": min(hit), "hi": max(hit), "w": width, "first": first, "mean": mean})
    start = {}
    for b in sorted(bands, key=lambda b: (b["mean"], b["k"])):
        s0 = b["first"]
        for o in bands:
            if o["k"] in start and not (o["hi"] < b["lo"] or o["lo"] > b["hi"]):
                s0 = max(s0, start[o["k"]] + o["w"])
        start[b["k"]] = s0
    by_k = {b["k"]: b for b in bands}
    col = {}
    for r, row in enumerate(rows):
        live = [(start[b["k"]], start[b["k"]] + b["w"]) for b in bands if b["lo"] <= r <= b["hi"]]
        ptr, seen = 0, {}
        for n in row:
            k = gof.get(n["id"])
            if k is not None and k in start:
                members = [m for m in row if gof.get(m["id"]) == k]
                i = seen.setdefault(k, 0)
                seen[k] += 1
                col[n["id"]] = start[k] + i + (by_k[k]["w"] - len(members)) / 2.0
                ptr = max(ptr, start[k] + by_k[k]["w"])
            else:
                c = ptr
                while any(lo <= c < hi for lo, hi in live):
                    c += 1
                col[n["id"]] = c
                ptr = c + 1
    # Nodes outside groups move toward the mean column of their neighbours (a barycenter pass),
    # keeping their order within the row and clear of the bands that cover the row.
    nbr = {}
    for e in edges or ():
        a, b = e.get("from"), e.get("to")
        if a in col and b in col:
            nbr.setdefault(a, []).append(b)
            nbr.setdefault(b, []).append(a)
    for _ in range(4):
        for r, row in enumerate(rows):
            live = [(start[b["k"]], start[b["k"]] + b["w"]) for b in bands if b["lo"] <= r <= b["hi"]]
            taken = {round(col[n["id"]] * 2) for n in row if gof.get(n["id"]) in start}
            free_nodes = [n for n in row if gof.get(n["id"]) not in start]
            want = {n["id"]: (sum(col[m] for m in nbr[n["id"]]) / len(nbr[n["id"]]) if nbr.get(n["id"]) else col[n["id"]])
                    for n in free_nodes}
            last = -1e9
            for n in sorted(free_nodes, key=lambda n: (want[n["id"]], row.index(n))):
                c = max(round(want[n["id"]]), int(last) + 1)
                while any(lo <= c < hi for lo, hi in live) or round(c * 2) in taken:
                    c += 1
                col[n["id"]] = c
                last = c
    lo = min(col.values(), default=0)
    return {k: v - lo for k, v in col.items()}


def _seg_boxes(pts):
    return [(min(p[0], q[0]) - 1, min(p[1], q[1]) - 1, max(p[0], q[0]) + 1, max(p[1], q[1]) + 1)
            for p, q in zip(pts or [], (pts or [])[1:])]


def group_frames(t, groups, pos, avoid=()):
    """A frame behind each group's members. Its name goes in the top corner (left, else right)
    that no arrow crosses; avoid holds the arrows' segment boxes."""
    parts = []
    for g in groups:
        boxes = []
        for m in g["members"]:
            if m in pos:
                cx, cy, n = pos[m]
                sh, hw, hh = _node_box(n)
                boxes.append((cx - hw, cy - hh, cx + hw, cy + hh))
        if not boxes:
            continue
        x0 = min(b[0] for b in boxes) - GROUP_PAD
        y0 = min(b[1] for b in boxes) - GROUP_HEAD
        x1 = max(b[2] for b in boxes) + GROUP_PAD
        y1 = max(b[3] for b in boxes) + GROUP_PAD - 4
        members = ",".join(esc(m) for m in g["members"])
        parts.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" rx="10" '
                     f'fill="{t["rule"]}" fill-opacity=".35" stroke="{t["muted"]}" stroke-opacity=".55" '
                     f'stroke-dasharray="4,3" data-group="{esc(g["id"])}" data-name="{esc(g["name"])}" data-members="{members}"/>')
        label = ((g["tag"] + "  " if g.get("tag") else "") + str(g["name"])).upper()
        lw = _text_w(label, 10, True) + 0.4 * len(label)

        def hits(lx):
            b = (lx - 8, y0 + 3, lx + lw + 8, y0 + 19)  # keep clear of arrows, not just off them
            return sum(1 for a in avoid if b[0] < a[2] and a[0] < b[2] and b[1] < a[3] and a[1] < b[3])
        # left corner if it is clear, else the nearest clear spot along the top band, else the least crossed
        spots = [x0 + 10] + [x0 + 10 + 8 * k for k in range(1, int(max(0, x1 - 20 - lw - x0) // 8) + 1)]
        lx = min(spots, key=lambda v: (hits(v), v - x0))
        parts.append(f'<text x="{lx:.1f}" y="{y0 + 15:.1f}" font-size="10" font-weight="600" '
                     f'font-family="{FONT}" fill="{t["muted"]}" letter-spacing=".04em">{esc(label)}</text>')
    return parts


def _wrap_px(text, max_w, fs, bold=False, max_lines=3):
    """Greedy word wrap by estimated pixel width. A word wider than a line is split.
    Past max_lines the last line ends in an ellipsis; validate warns before that happens."""
    words, lines, cur = str(text or "").split(), [], ""
    for wd in words:
        while _text_w(wd, fs, bold) > max_w and len(wd) > 1:
            cut = max(1, int(len(wd) * max_w / _text_w(wd, fs, bold)) - 1)
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(wd[:cut] + "-")
            wd = wd[cut:]
        trial = (cur + " " + wd).strip()
        if cur and _text_w(trial, fs, bold) > max_w:
            lines.append(cur)
            cur = wd
        else:
            cur = trial
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and _text_w(last + "...", fs, bold) > max_w:
            last = last[:-1]
        lines[-1] = last.rstrip() + "..."
    return lines or [""]


BOX_W, BOX_H = 160, 56


def _box_lines(name, sub="", w=BOX_W):
    return _wrap_px(name, w - 16, 12, True, 3), (_wrap_px(sub, w - 16, 9, False, 2) if sub else [])


def _box_h(name, sub="", tag="", w=BOX_W):
    """Height a box needs for its wrapped name and sub. One line each fits the classic 56."""
    nl, sl = _box_lines(name, sub, w)
    block = 15 * len(nl) + (12 * len(sl) + 2 if sl else 0)
    return max(BOX_H, block + (30 if tag else 18))


# Line glyphs on a 16x16 grid, drawn with the box's stroke. Generic shapes, no brand marks.
ICONS = {
    "user": "M8 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM2.5 14c.8-2.8 3-4 5.5-4s4.7 1.2 5.5 4",
    "database": "M3 4c0-1.1 2.2-2 5-2s5 .9 5 2-2.2 2-5 2-5-.9-5-2zM3 4v8c0 1.1 2.2 2 5 2s5-.9 5-2V4M3 8c0 1.1 2.2 2 5 2s5-.9 5-2",
    "server": "M2.5 2.5h11v4h-11zM2.5 9.5h11v4h-11zM5 4.5h1M5 11.5h1",
    "cloud": "M4.5 12.5h7a3 3 0 0 0 .4-6A4 4 0 0 0 4.3 7a2.8 2.8 0 0 0 .2 5.5z",
    "queue": "M2 4.5h12M2 8h12M2 11.5h12M11.5 2.5l2.5 2-2.5 2",
    "lock": "M4.5 7V5a3.5 3.5 0 0 1 7 0v2M3 7h10v7H3z",
    "globe": "M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zM1.5 8h13M8 1.5c2 2 2.5 4 2.5 6.5S10 12.5 8 14.5M8 1.5C6 3.5 5.5 5.5 5.5 8s.5 4.5 2.5 6.5",
    "mobile": "M5 1.5h6v13H5zM7.5 12.5h1",
    "web": "M1.5 3h13v10h-13zM1.5 6h13M3.5 4.5h1",
    "mail": "M1.5 3.5h13v9h-13zM1.5 4l6.5 5 6.5-5",
    "gear": "M8 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5zM8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4",
    "key": "M5.5 10.5a3 3 0 1 1 2.1-.9L14 3.2M11.5 5.5l2 2",
    "bot": "M3 6h10v7H3zM8 3v3M6 9.5h1M9 9.5h1M7 2.5h2",
    "file": "M4 1.5h5.5L12 4v10.5H4zM9.5 1.5V4H12",
    "chart": "M2.5 13.5h11M4.5 11V8M8 11V4.5M11.5 11V6.5",
    "shield": "M8 1.5l5.5 2v4c0 3.5-2.4 6-5.5 7-3.1-1-5.5-3.5-5.5-7v-4z",
    "bolt": "M9 1.5L3.5 9H8l-1 5.5L12.5 7H8z",
}
# Mermaid writers reach for Font Awesome names; these map onto the glyphs above
_FA_ICONS = {"user": "user", "users": "user", "person": "user", "database": "database", "db": "database",
             "server": "server", "cloud": "cloud", "lock": "lock", "globe": "globe", "mobile": "mobile",
             "phone": "mobile", "desktop": "web", "laptop": "web", "browser": "web", "envelope": "mail",
             "cog": "gear", "gear": "gear", "key": "key", "robot": "bot", "file": "file", "chart-bar": "chart",
             "shield": "shield", "bolt": "bolt", "list": "queue", "inbox": "queue"}


def node_box(t, x, y, w, h, name, sub="", tag="", focal=False, corners="editorial", nid=None, icon=None):
    fill = t["accent_tint"] if focal else t["card"]
    stroke = t["accent"] if focal else t["ink"]
    rx = corner_rx(corners)
    cx = x + w / 2
    mark = f' data-node="{esc(nid)}" data-label="{esc(name)}"' if nid is not None else ""
    s = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{t["paper"]}"/>',
         f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}"{mark}/>']
    if tag:
        s.append(f'<rect x="{x+8}" y="{y+6}" width="{max(28,len(tag)*7)}" height="12" rx="2" fill="none" stroke="{stroke}" stroke-opacity=".4" stroke-width=".8"/>')
        s.append(f'<text x="{x+8+max(28,len(tag)*7)/2}" y="{y+15}" font-size="8" font-family="{FONT}" fill="{stroke}" text-anchor="middle">{esc(tag)}</text>')
    if icon in ICONS:
        s.append(f'<path d="{ICONS[icon]}" transform="translate({x + w - 24},{y + 5})" fill="none" stroke="{stroke}" '
                 f'stroke-opacity=".75" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>')
    # the wrapped name and sub, centered in the space below the tag and icon
    nl, sl = _box_lines(name, sub, w)
    block = 15 * len(nl) + (12 * len(sl) + 2 if sl else 0)
    top = y + (20 if tag or icon in ICONS else 8)
    base = top + max(0.0, (y + h - 8 - top - block) / 2.0) + 11
    for i, line in enumerate(nl):
        s.append(f'<text x="{cx}" y="{base + 15 * i:.1f}" font-size="12" font-weight="600" font-family="{SANS}" fill="{t["ink"]}" text-anchor="middle">{esc(line)}</text>')
    for i, line in enumerate(sl):
        s.append(f'<text x="{cx}" y="{base + 15 * len(nl) + 2 + 12 * i:.1f}" font-size="9" font-family="{MONO}" fill="{t["muted"]}" text-anchor="middle">{esc(line)}</text>')
    return "\n".join(s)


def _diamond_lines(name):
    return _wrap_px(name, 100, 12, True, 3)


def _diamond_h(name):
    return {1: 64, 2: 84}.get(len(_diamond_lines(name)), 104)


def diamond(t, cx, cy, w, h, name, focal=False, nid=None):
    stroke = t["accent"] if focal else t["ink"]
    fill = t["accent_tint"] if focal else t["card"]
    pts = f"{cx},{cy-h/2} {cx+w/2},{cy} {cx},{cy+h/2} {cx-w/2},{cy}"
    lines = _diamond_lines(name)
    y0 = cy + 4 - 7.5 * (len(lines) - 1)
    text = "".join(f'<text x="{cx}" y="{y0 + 15 * i:.1f}" font-size="12" font-weight="600" font-family="{SANS}" fill="{t["ink"]}" text-anchor="middle">{esc(line)}</text>'
                   for i, line in enumerate(lines))
    return (f'<polygon points="{pts}" fill="{t["paper"]}"/>'
            f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}"'
            + (f' data-node="{esc(nid)}" data-label="{esc(name)}" data-cx="{cx}" data-cy="{cy}"' if nid is not None else "")
            + '/>' + text)


def _pill_w(text):
    return max(40, int(len(text) * 6.4 + 12))


def arrow_label(t, mx, ay, text, vertical=False, flip=False):
    """Label sitting off the shaft, on the paper, so it does not cut the arrow.
    flip puts it on the other side: left of a vertical shaft, below a horizontal one."""
    x0, y0, _, _ = _label_box(mx, ay, text, vertical, flip)
    w = _pill_w(text)
    return (f'<rect x="{x0}" y="{y0}" width="{w}" height="16" rx="2" fill="{t["paper"]}"/>'
            f'<text x="{x0 + w / 2}" y="{y0 + 12}" font-size="10" font-family="{MONO}" fill="{t["muted"]}" text-anchor="middle">{esc(text)}</text>')


def _label_box(mx, ay, text, vertical=False, flip=False):
    w = _pill_w(text)
    if vertical:
        x0 = mx - 8 - w if flip else mx + 8
        return (x0, ay - 9, x0 + w, ay + 7)
    y0 = ay + 8 if flip else ay - 24
    return (mx - w / 2, y0, mx + w / 2, y0 + 16)


def _place_label(mx, my, vertical, text, pts, avoid, soft=()):
    """The first spot along the route where the label's pill clears everything. Tries the
    default, then each segment's middle, on both sides and both orientations. If none is
    clear: never on a hard obstacle (a box or a label), then the fewest soft ones (other arrows)."""
    cands = [(mx, my, vertical, False), (mx, my, vertical, True)]
    for (px, py), (qx, qy) in zip(pts or [], (pts or [])[1:]):
        seg_v = abs(qy - py) > abs(qx - px)
        for v in (seg_v, not seg_v):
            for flip in (False, True):
                cands.append(((px + qx) / 2.0, (py + qy) / 2.0, v, flip))

    def hits(b, boxes):
        return sum(1 for a in boxes if b[0] < a[2] + 2 and a[0] - 2 < b[2] and b[1] < a[3] + 2 and a[1] - 2 < b[3])
    scored = []
    for k, c in enumerate(cands):
        b = _label_box(c[0], c[1], text, c[2], c[3])
        cost = (hits(b, avoid), hits(b, soft), k)
        if cost[:2] == (0, 0):
            return c
        scored.append((cost, c))
    return min(scored)[1]


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
    """Longest-path layering (Sugiyama layer assignment). Loops are broken first: a depth-first
    walk from the start nodes (no incoming arrow, else the first in the spec) marks each arrow
    that returns to a node still on the walk as a back edge. Ranking ignores back edges, so a
    loop's start stays on top and its return arrow is drawn going back up. Pure stdlib."""
    ids = [n["id"] for n in nodes]
    succ = {i: [] for i in ids}
    indeg = {i: 0 for i in ids}
    for e in edges:
        a, b = e.get("from"), e.get("to")
        if a in succ and b in succ and a != b:
            succ[a].append(b)
            indeg[b] += 1
    back, state = set(), {}
    for root in [i for i in ids if indeg[i] == 0] + ids:
        if root in state:
            continue
        state[root] = 1
        stack = [(root, iter(succ[root]))]
        while stack:
            v, it = stack[-1]
            w = next(it, None)
            if w is None:
                state[v] = 2
                stack.pop()
            elif state.get(w) == 1:
                back.add((v, w))
            elif w not in state:
                state[w] = 1
                stack.append((w, iter(succ[w])))
    preds = {i: [] for i in ids}
    for v in ids:
        for w in succ[v]:
            if (v, w) not in back:
                preds[w].append(v)
    rank = {}
    for nid in ids:  # the graph is acyclic now; an explicit stack avoids deep recursion
        stack = [nid]
        while stack:
            v = stack[-1]
            if v in rank:
                stack.pop()
                continue
            todo = [p for p in preds[v] if p not in rank]
            if todo:
                stack.extend(todo)
            else:
                rank[v] = max((rank[p] + 1 for p in preds[v]), default=0)
                stack.pop()
    return rank


def _render_flow_once(spec, corners="editorial", auto=False, theme=None):
    t = theme or THEME
    nodes = [dict(n) for n in spec["nodes"]]  # [{id,shape,name,tag?,sub?,focal?}]
    for n in nodes:
        n.setdefault("name", n.get("id", ""))
        sh = n.get("shape", "rect")
        n["_h"] = 8 if sh == "dot" else (_diamond_h(n["name"]) if sh == "diamond" else _box_h(n["name"], n.get("sub", ""), n.get("tag", "") or n.get("icon", "")))
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
    # A row of tall (wrapped) boxes pushes the rows below it down; classic rows keep their pitch.
    tall = {rk: max(n["_h"] for n in g) for rk, g in by_rank.items()}
    extra, acc, prev = {}, 0.0, None
    for rk in sorted(by_rank):
        if prev is not None:
            # push down only when the rows would leave less than 56px clear between them
            acc += max(0.0, (tall[prev] + tall[rk]) / 2.0 + 56 - (rk - prev) * gap_y)
        extra[rk], prev = acc, rk

    def row_y(rk):
        return top + rk * gap_y + 30 + extra.get(rk, 0.0)
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
                pos[n["id"]] = (cx, row_y(rk), n)
                placed[n["id"]] = cx
        else:
            # Some nodes carry a lane. The rest take the free lane nearest their parents,
            # so they do not stack on the center lane under a long edge.
            taken = {n["lane"] for n in group if "lane" in n}
            given = {}

            def _parent_x(n):
                xs = [placed[e["from"]] for e in edges if e.get("to") == n["id"] and e.get("from") in placed]
                return sum(xs) / len(xs) if xs else W / 2
            for n in sorted((g for g in group if "lane" not in g and len(group) > 1), key=_parent_x):
                px = _parent_x(n)
                free = [ln for ln in range(-4, 5) if ln not in taken]
                ln = min(free, key=lambda v: (abs(W / 2 + v * (col_w + 40) - px), abs(v)))
                taken.add(ln)
                given[n["id"]] = ln
            for n in group:
                lane = n.get("lane", given.get(n["id"], 0))
                cx = W / 2 + lane * (col_w + 40)
                pos[n["id"]] = (cx, row_y(rk), n)
                placed[n["id"]] = cx
    # Two boxes in one row never share a spot (a lane on some nodes and not others did that).
    # Push them apart, then shift and widen the canvas to fit.
    for rk, group in by_rank.items():
        row = sorted((pos[n["id"]][0], k, n["id"]) for k, n in enumerate(group))
        for k in range(1, len(row)):
            if row[k][0] < row[k - 1][0] + 200:
                row[k] = (row[k - 1][0] + 200, row[k][1], row[k][2])
        for cx, _, nid in row:
            pos[nid] = (cx, pos[nid][1], pos[nid][2])
    if pos:
        shift = max(0, 110 - min(cx for cx, _, _ in pos.values()))
        if shift:
            pos = {k: (cx + shift, cy, n) for k, (cx, cy, n) in pos.items()}
        W = max(W, int(max(cx for cx, _, _ in pos.values()) + 110 + (200 if _notes else 0)))
    low = max((cy + n["_h"] / 2 - BOX_H / 2 for _, cy, n in pos.values()), default=top)
    if _notes:
        low = max(low, top + 14 + max(0, len(_notes) - 1) * 92 + 52)
    H = int(low + 112)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" viewBox="0 0 {W} {H}" width="{W}"><title>{esc(spec.get("title","flow"))}</title>',
             f'<desc>{esc(spec.get("sub", spec.get("title", "flow")))}</desc>',
             f'<rect width="{W}" height="{H}" fill="{t["paper"]}"/>', markers(t)]
    parts.extend(head_bits)
    frame_at, seg_boxes = len(parts), []
    node_boxes = [(cx - 80, cy - n["_h"] / 2, cx + 80, cy + n["_h"] / 2) for cx, cy, n in pos.values()]
    label_boxes = []
    for nid, (cx, cy, n) in pos.items():
        sh = n.get("shape", "rect")
        h = n["_h"]
        if sh == "diamond":
            parts.append(diamond(t, cx, cy, 160, h, n["name"], n.get("focal", False), nid))
        elif sh == "oval":
            # both rects: the paper underlay and the visible box
            parts.append(node_box(t, cx-80, cy-h/2, 160, h, n["name"], n.get("sub",""), n.get("tag",""), n.get("focal",False), corners, nid, n.get("icon")).replace(f'rx="{corner_rx(corners)}"','rx="20"', 2))
        elif sh == "dot":
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="4" fill="{t["ink"]}"/>')
        else:
            parts.append(node_box(t, cx-80, cy-h/2, 160, h, n["name"], n.get("sub",""), n.get("tag",""), n.get("focal",False), corners, nid, n.get("icon")))
    # edges after nodes. Ports are spread so an input and an output do not share a point.
    # An arrow going back up (a loop) leaves and enters on the outer side and runs up the outside,
    # instead of climbing through the boxes between its ends.
    fixed = {}
    row_ys = sorted({round(cy, 1) for _, cy, _ in pos.values()})
    for i, e in enumerate(edges):
        a, b = pos.get(e.get("from")), pos.get(e.get("to"))
        if a and b and b[1] < a[1] - 1 and a[2].get("shape") != "dot" and b[2].get("shape") != "dot":
            side = "w" if (a[0] + b[0]) / 2 <= W / 2 else "e"
            fixed[i] = (side, side)
        elif (a and b and b[1] > a[1] + 1 and a[2].get("shape") not in ("diamond", "dot") and b[2].get("shape") != "dot"
              and not any(a[1] + 1 < y < b[1] - 1 for y in row_ys)):
            fixed[i] = ("s", "n")  # to the next row: out the bottom, in the top. Longer arrows go round the side.
    ports = assign_ports(pos, edges, fixed=fixed, trunk=True)
    tracks = _gap_tracks(ports, room=30, net_by_source=True)
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
        d, lx, ly, vertical = route_edge(x1, y1, s1, x2, y2, s2, nudge=nudge, track=tracks.get(i, 0))
        if not d:
            continue
        dash = ' stroke-dasharray="5,4"' if e.get("async") else ""
        ends = f' data-from="{esc(e.get("from"))}" data-to="{esc(e.get("to"))}" data-label="{esc(e.get("label", ""))}"'
        parts.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="1.8"{dash} marker-end="url(#{mid})"{ends}/>')
        parts.append(_tail(x1, y1, s1, col))
        seg_boxes += _seg_boxes(route_edge.last_pts)
        if e.get("label"):
            text = e["label"].upper()
            lx, ly, vertical, flip = _place_label(lx, ly + label_dy, vertical, text, route_edge.last_pts,
                                                  node_boxes + label_boxes)
            parts.append(arrow_label(t, lx, ly, text, vertical=vertical, flip=flip))
            label_boxes.append(_label_box(lx, ly, text, vertical, flip))
    parts[frame_at:frame_at] = group_frames(t, _groups_of(spec, set(pos)), pos, seg_boxes)
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
    _render_flow_once.pos = {nid: (cx, cy) for nid, (cx, cy, _n) in pos.items()}
    return "\n".join(parts), W, H


_render_flow_once.pos = {}


def render_flow(spec, corners="editorial", auto=False, theme=None):
    """Draw a flow. If an arrow runs through a box, move a node the spec left free to
    another lane and draw again. A node with its own lane is never moved. A move must lower
    the layout cost (problems, crossings, arrow length), not just the problem count."""
    def draw(sp):
        out, found, c = _layout_cost(_render_flow_once(sp, corners, auto, theme))
        return out, dict(_render_flow_once.pos), found, c
    out, pos, bad, cost = draw(spec)
    if not bad:
        return out
    work = json.loads(json.dumps(spec))
    free = {n["id"] for n in work.get("nodes", []) if "lane" not in n}
    for _ in range(4):
        blockers = []
        for it in bad:
            x, y = it["at"]
            for nid, (cx, cy) in pos.items():
                if nid in free and nid not in blockers and abs(cx - x) <= 80 and abs(cy - y) <= 32:
                    blockers.append(nid)
        best = None
        # the nodes at the problem first; if moving them does not help, any free node
        for nid in blockers + [n for n in pos if n in free and n not in blockers]:
            for lane in (-1, 1, -2, 2):
                trial = json.loads(json.dumps(work))
                for n in trial["nodes"]:
                    if n.get("id") == nid:
                        n["lane"] = lane
                o, p, b, c = draw(trial)
                if c < cost and (best is None or c < best[4]):
                    best = (nid, trial, (o, p), b, c)
            if best:
                break
        if not best:
            break
        nid, work, (out, pos), bad, cost = best
        free.discard(nid)
        if not bad:
            break
    return out


def render_arch(spec, corners="editorial", theme=None):
    """Draw an architecture view. If the audit finds a problem (an arrow through a box, two
    arrows on one line, a label collision), try other orders within each row (layers never
    change). Keep the order with the lowest cost: a problem counts as four crossings, and
    arrow length breaks ties, so one fix is never bought with a tangle of new crossings."""
    out, bad, cost = _layout_cost(_render_arch_once(spec, corners, theme))
    if not bad or not isinstance(spec.get("nodes"), list):
        return out
    work = json.loads(json.dumps(spec))
    for _ in range(6):
        improved = False
        rows = {}
        for k, n in enumerate(work["nodes"]):
            rows.setdefault(n.get("layer", 0), []).append(k)
        for idx in rows.values():
            for a in range(len(idx)):
                for b in range(a + 1, len(idx)):
                    trial = json.loads(json.dumps(work))
                    ns = trial["nodes"]
                    ns[idx[a]], ns[idx[b]] = ns[idx[b]], ns[idx[a]]
                    o, found, c = _layout_cost(_render_arch_once(trial, corners, theme))
                    if c < cost:
                        work, out, bad, cost, improved = trial, o, found, c, True
        if not improved:
            break
    return out


def _layout_cost(out):
    """(drawing, audit problems, cost) for the layout repair loops."""
    import xml.etree.ElementTree as ET
    stats = {"crossings": 0, "wire": 0.0}
    try:
        found = _svg_geometry(ET.fromstring(out[0]), out[1], out[2], stats)
    except ET.ParseError:
        found = []
    bad = [i for i in found if i["code"] in ("through", "strike", "overlap", "collide", "shared", "intrude")]
    return out, bad, 4 * len(bad) + stats["crossings"] + stats["wire"] / 400.0


def _gap_tracks(ports, room=None, net_by_source=False):
    """Arrows that cross the same gap between rows each get a track (a turn height), so two
    arrows never run on one line. Greedy interval colouring over their sideways spans.
    net_by_source: arrows leaving one port share a track (a trunk that splits, like a tree).
    room caps the spread when the gap is tight. Returns {edge index: vertical offset}."""
    tracks, by_gap = {}, {}
    for i, (x1, y1, s1, x2, y2, s2) in ports.items():
        if s1 in ("n", "s") and s2 in ("n", "s") and abs(x1 - x2) >= 0.5:
            by_gap.setdefault((round(min(y1, y2)), round(max(y1, y2))), []).append((min(x1, x2), max(x1, x2), i, x1, x2))
    for spans in by_gap.values():
        if net_by_source:
            # one span per source port: its arrows ride one trunk
            nets = {}
            for lo, hi, i, sx, dx in spans:
                key = (round(sx, 1), round(ports[i][1], 1))
                n0 = nets.setdefault(key, [lo, hi, [], sx, dx])
                n0[0], n0[1] = min(n0[0], lo), max(n0[1], hi)
                n0[2].append(i)
            members = {n[2][0]: n[2] for n in nets.values()}
            spans = [(n[0], n[1], n[2][0], n[3], n[4]) for n in nets.values()]
        else:
            members = {i: [i] for _, _, i, _, _ in spans}
        # An arrow that leaves at the x where another arrives must turn above it, or the
        # two run down one line. Place those first, then the rest by their left end.
        above = {i: set() for _, _, i, _, _ in spans}
        for _, _, a, sa, _ in spans:
            for _, _, b, _, db in spans:
                if a != b and abs(sa - db) < 14:
                    above[b].add(a)
        order, placed_ids = [], set()
        pending = sorted(spans)
        while pending:
            ready = [x for x in pending if above[x[2]] <= placed_ids] or pending[:1]
            x = ready[0]
            pending.remove(x)
            order.append(x)
            placed_ids.add(x[2])
        used, k_of = [], {}  # per track: the spans already on it
        for lo, hi, i, _, _ in order:
            floor = max((k_of[a] + 1 for a in above[i] if a in k_of), default=0)
            k = next((k for k in range(floor, len(used))
                      if all(hi + 14 < a or lo - 14 > b for a, b in used[k])), None)
            if k is None:
                while len(used) < floor:
                    used.append([])
                used.append([])
                k = len(used) - 1
            used[k].append((lo, hi))
            k_of[i] = k
        n = len(used)
        step = 14.0 if room is None or n < 2 else min(14.0, room / (n - 1))
        for _, _, i, _, _ in spans:
            for m in members[i]:
                tracks[m] = (k_of[i] - (n - 1) / 2.0) * step
    return tracks


def _render_arch_once(spec, corners="editorial", theme=None):
    t = theme or THEME
    nodes = [dict(n) for n in spec["nodes"]]; edges = spec.get("edges", [])
    for n in nodes:
        n.setdefault("name", n.get("id", ""))
        n["_h"] = _box_h(n["name"], n.get("sub", ""), n.get("tag", "") or n.get("icon", ""))
    _notes = (spec.get("notes", []) or [])[:2]
    head_bits, head_h = figure_heading(t, spec.get("title") or "", spec.get("sub") or "", x=30)
    # simple layered: group by 'layer' (0 top..n), spread across width
    from collections import defaultdict
    layers = defaultdict(list)
    for n in nodes:
        layers[n.get("layer", 0)].append(n)
    groups = _groups_of(spec, {n["id"] for n in nodes})
    if groups:
        # members of one group sit side by side; the row otherwise keeps the spec's order
        gof = {m: k for k, g in enumerate(groups) for m in g["members"]}
        for key, row in layers.items():
            first = {}
            for j, n in enumerate(row):
                first.setdefault(gof.get(n["id"], ("solo", j)), j)
            layers[key] = sorted(row, key=lambda n, r=row: (first[gof.get(n["id"], ("solo", r.index(n)))], r.index(n)))
    max_n = max((len(row) for row in layers.values()), default=1)
    # A box is 160 wide. A row wider than four overlaps on a 760 canvas.
    # A spec with the count cap off gets a wider pitch so the labels fit.
    pitch = 220 if spec.get("budget", True) is False else 188
    W = max(760, pitch * (max_n + 1)) + (200 if _notes else 0)
    cols = None
    if groups:
        # with groups, rows share one column grid so a group's frame holds only its members
        pitch = max(pitch, 210)
        cols = _group_columns(layers, groups, gof, edges)
        span = max(cols.values()) + 1 if cols else 1
        W = max(760, int(span * pitch + 2 * 50)) + (200 if _notes else 0)
    pos = {}
    top, gap_y = max(100, head_h + 24), 156
    acc, prev_h = 0.0, None
    for li, key in enumerate(sorted(layers)):
        row = layers[key]
        row_h = max(n["_h"] for n in row)
        if prev_h is not None:
            acc += max(0.0, (prev_h + row_h) / 2.0 + 100 - gap_y)  # keep 100px clear for the arrows' tracks
        prev_h = row_h
        for j, n in enumerate(row):
            x = (50 + (cols[n["id"]] + 0.5) * pitch) if cols else (W / (len(row)+1)) * (j+1)
            y = top + li * gap_y + acc
            pos[n["id"]] = (x, y, n)
    low = max((y + n["_h"] / 2 - BOX_H / 2 for _, y, n in pos.values()), default=top)
    if _notes:
        low = max(low, top + 14 + max(0, len(_notes) - 1) * 92 + 52)
    H = int(low + 112)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" viewBox="0 0 {W} {H}" width="{W}"><title>{esc(spec.get("title","arch"))}</title>',
             f'<desc>{esc(spec.get("sub", spec.get("title", "arch")))}</desc>',
             f'<rect width="{W}" height="{H}" fill="{t["paper"]}"/>', markers(t)]
    parts.extend(head_bits)
    frame_at = len(parts)
    for nid,(x,y,n) in pos.items():
        parts.append(node_box(t, x-80, y-n["_h"]/2, 160, n["_h"], n["name"], n.get("sub",""), n.get("tag",""), n.get("focal",False), corners, nid, n.get("icon")))
    node_boxes = [(x - 80, y - n["_h"] / 2, x + 80, y + n["_h"] / 2) for x, y, n in pos.values()]
    label_boxes = []
    ports = assign_ports(pos, edges, layered=True)
    tracks = _gap_tracks(ports)
    routes = []
    for i, e in enumerate(edges):
        if i not in ports:
            continue
        x1, y1, s1, x2, y2, s2 = ports[i]
        col = t["link"] if e.get("proto","").startswith("http") else (t["accent"] if e.get("focal") else t["muted"])
        dash = ' stroke-dasharray="5,4"' if e.get("async") else ""
        mid = "al" if e.get("proto", "").startswith("http") else ("aa" if e.get("focal") else "a")
        d, lx, ly, vertical = route_edge(x1, y1, s1, x2, y2, s2, track=tracks.get(i, 0))
        if not d:
            continue
        ends = f' data-from="{esc(e.get("from"))}" data-to="{esc(e.get("to"))}" data-label="{esc(e.get("label", ""))}"'
        parts.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="1.8"{dash} marker-end="url(#{mid})"{ends}/>')
        parts.append(_tail(x1, y1, s1, col))
        pts = route_edge.last_pts
        segs = [(min(p[0], q[0]) - 1, min(p[1], q[1]) - 1, max(p[0], q[0]) + 1, max(p[1], q[1]) + 1)
                for p, q in zip(pts, pts[1:])]
        routes.append((e, lx, ly, vertical, pts, segs))
    parts[frame_at:frame_at] = group_frames(t, groups, pos, [b for r in routes for b in r[5]])
    # Labels go last, once every arrow is routed: each one keeps clear of the boxes,
    # the labels already placed, and every other arrow.
    for k, (e, lx, ly, vertical, pts, _segs) in enumerate(routes):
        if e.get("label"):
            text = e["label"].upper()
            others = [b for j, r in enumerate(routes) if j != k for b in r[5]]
            lx, ly, vertical, flip = _place_label(lx, ly, vertical, text, pts, node_boxes + label_boxes, others)
            parts.append(arrow_label(t, lx, ly, text, vertical=vertical, flip=flip))
            label_boxes.append(_label_box(lx, ly, text, vertical, flip))
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
    msg_start = top + 86  # the first message's label sits clear of the actor boxes
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
    """Draw tables and relations. If the audit finds a problem, try other table orders and keep
    the one with the lowest layout cost (problems, crossings, length), as render_arch does."""
    out, bad, cost = _layout_cost(_render_schema_once(spec, corners, theme))
    tables = spec.get("tables") if isinstance(spec, dict) else None
    if not bad or not isinstance(tables, list) or any("x" in tb for tb in tables if isinstance(tb, dict)):
        return out
    work = json.loads(json.dumps(spec))
    for _ in range(4):
        improved = False
        n = len(work["tables"])
        for a in range(n):
            for b in range(a + 1, n):
                trial = json.loads(json.dumps(work))
                trial["tables"][a], trial["tables"][b] = trial["tables"][b], trial["tables"][a]
                o, found, c = _layout_cost(_render_schema_once(trial, corners, theme))
                if c < cost:
                    work, out, bad, cost, improved = trial, o, found, c, True
        if not improved or not bad:
            break
    return out


def _render_schema_once(spec, corners="editorial", theme=None):
    t = theme or THEME
    tables = spec.get("tables", [])
    relations = spec.get("relations", [])
    head_bits, head_h = figure_heading(t, spec.get("title") or "", spec.get("sub") or "", x=30)
    base_y = max(90, head_h + 16)
    rx = corner_rx(corners)
    tbl_w, row_h = 240, 24
    # the gap between columns fits the widest relation label, so labels never sit on a table
    widest = max((_pill_w(str(r.get("label", "")).upper()) for r in relations if r.get("label")), default=0)
    col_gap, row_gap = min(170, max(70, widest + 36)), 60
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
    rel_labels = []
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
            if x1 == x2 or y1 == y2:
                pts = [(x1, y1), (x2, y2)]
            else:
                ex = x2 if abs(x2 - x1) < 60 else (x1 + x2) / 2
                pts = [(x1, y1), (ex, y1), (ex, y2), (x2, y2)]
            text = rel["label"].upper()
            boxes = [(b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]) for b in table_boxes.values()]
            lx, ly, vert, flip = _place_label((x1 + x2) / 2, (y1 + y2) / 2, False, text, pts, boxes + rel_labels)
            parts.append(arrow_label(t, lx, ly, text, vertical=vert, flip=flip))
            rel_labels.append(_label_box(lx, ly, text, vert, flip))
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
        # Every point is drawn: up to 400 as dots with a tooltip, up to 5,000 as small translucent
        # dots so density shows, past that a fixed random sample of 5,000 (the footer says so).
        many = len(dset) > 400
        shown = dset if len(dset) <= 5000 else __import__("random").Random(7).sample(dset, 5000)
        # error bars first, then points
        for d in ([] if many else dset):
            if "ye" in d:
                y1 = sy(d["y"] - d["ye"]); y2 = sy(d["y"] + d["ye"])
                col = palette.get(d.get("g", ""), t["muted"])
                p.append(f'<line x1="{sx(d["x"]):.1f}" y1="{y1:.1f}" x2="{sx(d["x"]):.1f}" y2="{y2:.1f}" stroke="{col}" stroke-width="1"/>')
                p.append(f'<line x1="{sx(d["x"])-4:.1f}" y1="{y1:.1f}" x2="{sx(d["x"])+4:.1f}" y2="{y1:.1f}" stroke="{col}"/>')
                p.append(f'<line x1="{sx(d["x"])-4:.1f}" y1="{y2:.1f}" x2="{sx(d["x"])+4:.1f}" y2="{y2:.1f}" stroke="{col}"/>')
        for d in shown:
            hit = _hit(highlights, d.get("g"), d["x"], fmt_tick(d["x"]))
            if not markers and not hit:
                continue
            col = t["accent"] if hit else palette.get(d.get("g", ""), t["muted"])
            if many and not hit:
                p.append(f'<circle cx="{sx(d["x"]):.1f}" cy="{sy(d["y"]):.1f}" r="2.2" fill="{col}" fill-opacity=".35"/>')
                continue
            rad = 6.4 if hit else 4.2
            tip = (f'{d["g"]} · ' if d.get("g") else "") + f'{fmt_tick(d["x"])}, {fmt_tick(d["y"])}'
            p.append(f'<circle cx="{sx(d["x"]):.1f}" cy="{sy(d["y"]):.1f}" r="{rad}" fill="{col}" fill-opacity=".9" stroke="{t["card"]}" stroke-width="1">'
                     f'<title>{esc(tip)}</title></circle>')
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
    note = f"n = {n}" + (" · 5,000 shown, a random sample" if n > 5000 else "")
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
                    tip = (f'{d["g"]} · ' if d.get("g") else "") + f'{d["cat"]}: {fmt_tick(d["val"])}' + (f" {unit}" if unit else "")
                    parts.append(f'{shape} fill="{col}" fill-opacity="{"0.95" if hit else "0.85"}"{edge}><title>{esc(tip)}</title></path>')
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
                    tip = (f'{d["g"]} · ' if d.get("g") else "") + f'{d["cat"]}: {fmt_tick(d["val"])}' + (f" {unit}" if unit else "")
                    parts.append(f'{shape} fill="{col}" fill-opacity="{"0.95" if hit else "0.85"}"{edge}><title>{esc(tip)}</title></path>')
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


def _lttb(pts, n):
    """Largest-Triangle-Three-Buckets: the n points that keep a long line's shape (peaks and dips)."""
    if len(pts) <= n or n < 3:
        return pts
    out, a, every = [pts[0]], 0, (len(pts) - 2) / (n - 2)
    for i in range(n - 2):
        lo, hi = int(i * every) + 1, int((i + 1) * every) + 1
        nlo, nhi = hi, min(int((i + 2) * every) + 1, len(pts))
        ax = sum(p[0] for p in pts[nlo:nhi]) / max(1, nhi - nlo)
        ay = sum(p[1] for p in pts[nlo:nhi]) / max(1, nhi - nlo)
        px, py = pts[a]
        best = max(range(lo, hi), key=lambda j: abs((px - ax) * (pts[j][1] - py) - (px - pts[j][0]) * (ay - py)))
        out.append(pts[best])
        a = best
    out.append(pts[-1])
    return out


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
    multi = len(groups) > 1 and groups != ["default"]
    ends = {}
    if multi:
        for g in groups:
            last = [d for d in rows if d.get("g", "default") == g][-1]
            ends[g] = f"{g} {fmt_tick(last['y'])}"
    right = max([40] + [int(_text_w(v, 11, True)) + 24 for v in ends.values()])
    if multi:
        H = head_h + 360 + 60  # the end labels name the series; no legend row below the axis
    pw, ph = W - ox - right, 320
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
    end_marks = []
    for g in groups:
        g_rows = [d for d in rows if d.get("g", "default") == g]
        if not g_rows:
            continue
        pts = []
        for d in g_rows:
            xp = sx(d["x_num"]) if is_numeric_x else sx(d["x_str"])
            yp = sy(d["y"])
            pts.append((xp, yp))
        # a highlighted series is coral end to end: line, dots, and legend swatch
        col = t["accent"] if len(groups) > 1 and _hit(highlights, g) else palette[g]
        if len(groups) == 1:
            poly_pts = f"{pts[0][0]:.1f},{oy+ph} " + " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in pts) + f" {pts[-1][0]:.1f},{oy+ph}"
            parts.append(f'<polygon points="{poly_pts}" fill="{col}" fill-opacity="0.08"/>')
        drawn = _lttb(pts, 600)  # a long series keeps its shape at a fraction of the points
        path_d = f"M{drawn[0][0]:.1f},{drawn[0][1]:.1f} " + " ".join(f"L{p[0]:.1f},{p[1]:.1f}" for p in drawn[1:])
        parts.append(f'<path d="{path_d}" fill="none" stroke="{col}" stroke-width="2.2" stroke-linecap="round"/>')
        dense = len(pts) > 80  # past this the dots merge into a band; keep the highlighted ones
        for i, (xp, yp) in enumerate(pts):
            d = g_rows[i]
            hit = _hit(highlights, d["x_str"], d.get("g"), d["x_num"])
            if (not markers or dense) and not hit:
                continue
            mcol = t["accent"] if hit else col
            rad = 5.6 if hit else 3.5
            tip = (f"{g} · " if multi else "") + f"{d['x_str']}: {fmt_tick(d['y'])}"
            parts.append(f'<circle cx="{xp:.1f}" cy="{yp:.1f}" r="{rad}" fill="{mcol}" stroke="{t["card"]}" stroke-width="1.2">'
                         f'<title>{esc(tip)}</title></circle>')
        if multi:
            end_marks.append([yp, xp, g, col])
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
    end_marks.sort()
    for k in range(1, len(end_marks)):
        end_marks[k][0] = max(end_marks[k][0], end_marks[k - 1][0] + 14)
    for ly, lx, g, col in end_marks:
        parts.append(f'<text x="{ox + pw + 10:.1f}" y="{ly + 4:.1f}" font-size="11" font-weight="600" font-family="{SANS}" '
                     f'fill="{col}">{esc(ends[g])}</text>')
    xlab = _with_unit(xlabel or _humanize(xc), xunit)
    ylab = _with_unit(ylabel or _humanize(yc), yunit)
    parts.append(f'<text x="{ox+pw/2}" y="{oy+ph+40}" font-size="12" font-weight="600" font-family="{SANS}" fill="{t["ink"]}" text-anchor="middle">{esc(xlab)}</text>')
    if multi and not end_marks:
        lx, ly = ox, oy + ph + 66
        for g in groups:
            gcol = t["accent"] if _hit(highlights, g) else palette[g]
            parts.append(f'<line x1="{lx}" y1="{ly}" x2="{lx+16}" y2="{ly}" stroke="{gcol}" stroke-width="2.5"/>')
            parts.append(f'<circle cx="{lx+8}" cy="{ly}" r="3.5" fill="{gcol}" stroke="{t["card"]}" stroke-width="1"/>')
            parts.append(f'<text x="{lx+24}" y="{ly+4}" font-size="11" font-family="{SANS}" fill="{t["ink"]}">{esc(g)}</text>')
            lx += 24 + len(g) * 7 + 24
    parts.append(f'<text x="24" y="{oy+ph/2}" font-size="12" font-weight="600" font-family="{SANS}" fill="{t["ink"]}" text-anchor="middle" transform="rotate(-90 24,{oy+ph/2})">{esc(ylab)}</text>')
    src_note = f"n = {len(rows)}" + (f" · Source: {source}" if source else "")
    parts.append(f'<text x="36" y="{H-14}" font-size="10.5" font-family="{MONO}" fill="{t["soft"]}">{esc(src_note)}</text>')
    parts.append("</svg>")
    return "\n".join(parts), W, H, len(rows)


# Coastline packed as zlib+base64 of "lon_tenth,lat_tenth ..." rings separated by ";".
# Natural Earth 110m land, simplified. Drawn under the points. Not a tiled basemap.
LAND_B64 = """eNpNnVmS7CoMBbdSC+iOMKNx1P739ZQpue/7MoUBM2o8on7Xs39+z3V9fvfVI9VIzUXeE6k9SI1ItYfUpFzUuJ/9+X3rfn/bejqZ6/Pbdmv1vu0+SQ6S447kMXdQ4HTLUu1Eq9HCouz1+dfY93cu30fmHA+pRcqCjdSovq9rVd9Xf97UZDwX/ZwXqfjgYhT385C6qpfz3O83Nqn7fP6+GyPrdnEwsvZQe9wkrWRuZ97u2Ug2pmYyht73W7Y7C2N8/jVGu2v/tUD/7vGQvMdf7rYA0/SW/f4+D0VbFH32iVS/SNFop851nb9kM8lXrz6qUuTS7xbdelv6/u7DhLrwx4Is8rF2fPx2OWnydhymnMYeQ76n344a97rePFN8I3pPilZ6e1P26+ItfdmP7XVS0YP7ih7sw9Z7fMvWq/59f9eJediThaT3e77bcU/KdfMOqaixVyPF27X+UrRMX/aOVtyUe/N2UePepMg7HoND6qac/aPGX+/3ddfybCedpbYHt71ia96T9iaztujfQzm+e3uEdry9b2ZoMxubOb2dP2rcg/lzQz7M86kzc29m41DufurwxE5lM/eq64FdzN9hZdbhINDTSQ8OKzM7KVZr9v7mXb6NGsMaLVrpZ1V7nfY8MJWKvOG+ZAXHeupQjmVPeUvL933TylOj7KzMvTksNynWqDHj92TTOnKPkqP0SJg3PF6j9lq73KfM0Hy32qwcpxHaZT8kBKs29bQW+632ortzfyBy97U+tzvu+bjfrvaRIgV5aS7wdT7N9Q2S0jwKQVHamFVm3pVY7PQglM0pIecZ2W5v1XASh9hF/W756eHefe5IsOme+RkQvNj6nzGf3IZjjTwlY9d2HPeb8GA85zOeOlPzssH2mbYchHfu2uKTudqxLtNDFFtuMcC9n0g8eSBWO3lG1vQonc/a1NrXZ/lRXkGrdqzqghju2LALArnv+dlt5iGSA5iYrV4dyzyfOuDXm+iR2DkJ+3bCRySenKgYSSXcSq3Vq0Y7TxK6uxUFukcVvp3DmPn73jktN+0Emfsc5/nun7PfBBuSSTicJgZ4jq+uz7GHUeaB3DFjzzo5nCfHHjlvmSC3vFuxSy6Lb3aQSxaNt3b1nLXWpH9xFlobRZta40Tl232/qefk9Mb2e+obvTv37ERpUyxZ63Z3xzYduZ6T7Vnr2Ab7cgcditRd/Rt7vzUc/M0+XjUNbdpnvjb3lVsnUjtXr02/dtjnUtug2W05DlNz5K6LAdWGTrYea0zqPSxbjsmJ2nI+DpncgEPdivfEDO1nJI1tMWFJY9uW9wRtD4liJ2WN1EoqGm/vpJhRYydFim+wQ87huycpZvTlpLCTIgoUs7nJzqDGAz0d9IoZP8Hbm1zt0IObeTnBj9q5TN2VehSK3uTn99/7oHtswSORu2/bXFLD5y8XjlG5/V+uLUgRHcaBubR1aGwpQCGzHAnqlGovCsxhAfowszGrXfZhmHzedl2+o8yyunMhTbZaVzDbcghpNkxUOSta2MUtYnu87CeSp0StNlO0y06O4hPZdeWuSEJFt31wiW57ltyvvX24b7vTaOGmsXm/bDS+RmNw8iadu9dt0h1iWajovbrJkfsmkm4/52xIWJyoofQ3U2BrL29KhqVw12wXOSSO7j+ZUP7kGjc7OWVVdtIPX/ZhKocpASyls6v95WY1y8ooXflLcuYnLqekb8Q3jwaC4K0gQp6MzFSKnNHQ00xFTx6/gxh6lK9p5TjxI8Z09lVs9qxX4D3tZcJHhsvb+3kF1BQ/aPnO6UB8c4TUuPupt0mx+ca+XwFyy/e6eSOZcIl5V6sUfCBrbISdfRePyRoQqBCyFPj2n+iHrC8n5LsLJrIZb3Is+rzkA+P5/ImSIf5Sbg3ERnbvUnxDhF0spYLhYvnyranbt0/1ZSncsZsXR24zu2spMPOWzXNDjFY/JU4v1lVRd3VFXVPMC71arMzbqxJ6F4fOEa3mKOkBEv2CQK2uSOzbU6Lp6mpt/S/PGpYzb33+Wv7alQnjhZuFlJhsdgb9vtGsZhzYt8w3OER8ckKpPe4zuhYUh7eXfIG8bt5FaiIb0dqAk7AAQYioa94u7hJaXaSYptn6mwoW/ve1b9Ddq74hBZ5BcYJW/uXNf3mmpNm0MqDUnKHQIYuOZ4rtPaHeyuMT/utSTPjqhv9OeQoEJd+y8HPBXRxvLGPLCRrwBbSiGRPb1HZmI49jMC/yqvcxjhlfG7R8Qw3HbWqSRzkkiwFPlrsMuO4NLR1w3ZsDMQ4tn7+3HJdx328eXE29Yjz0j3ke8N/79u1TLedcLeeKujn3f3n2eT5vjUEPHsfxvC07DripdcfNN6CtOQ5k3DHfkVeKvHW95db4/M3Gt0kUeu81911OzPHr9G+z0v1i7pcp+H7ViDll1zVkpJst3HJeouV2es1apQZvGe9tOfrM0Y1Rf/5aifY4Vs1VyPautz32hty8IblViq9VjS8c/iG5Xr7fUt/hfLZ9ff4VYMwni0ZqVUubtWu5385fOfo4n5KTgk0yS+cvRc/m/vyV+8rhQ8D7aBoJBhqJmcUXEigdmXYj2ONEHuPVzD4+H1l27OhIOHVR2LmOHnggwyLxma5IrKZ2mB5HfqIN9dhDWmvC2BFlZq7aRI9osQ2txbz7KjhpKCaO6MQn7hyGlCOY80fCEcLpR/oSPPqj2NmCE00oVFhGoocMJ3jJO+SgUOwzSjc70qa0xTnqRVHaemXdkPtIPTnwlBlirT8pUzTkRulce66SejvanWajjuQ6oRmMujmPIZp/UsBiSprzHwofqXdXK3N1KJ6CTeccLChUZ09l6h4lT/fTqtxou6TtYXvoDwPKsy5P003qqpPowg3HccabYqaH4/BkI73PdRVtcdY8z/PaRWXmX3vj8Zw2Uq2+No4pNAlOzoAyajsYSMeD5cw86Ze6Bws6oPqDvT3gBIPZHdNyUgryVi+akSno9UCFDP2Y1Kg5GEhMA5rb2bHOkEr1YBX6NoW+NHvNVR93tac5byDRq6H7tfa8tKpJS+l92y/Vas4VeyhTjEPrxUBXyFQzj69du8p16GabrqWpXqvaPEGsdPMIpS7IDoMiaFvgoFUN9mmm4qzUW+Y5awzrusP8BnsIHpg1+l8PzJO+wl3bPd+UuxidTC2zhTQQWmYvuqm+KX3tQ4o2Sc2/vCepRaReKtbHKRrZWS1PWffIM6LODDX0pb7uOqGV6rVusR//Uq1W1TPdpdLsks6e9CR3yRSz0SVq7rBLmsFOlOIxQ4OdDdWIX5INNONuXntTzX1F7znTA1G6IeMMqQrzpyUm6yIbxNyxn5kXTveQnrEj3M+VaknIou6skQ+pD70fUjf18KfVTI5nFH+a9h6eNV0Z89qoVZjtfqkZ8ozfmPa+3+9bZTBkkoZMMqEgTdkKquKINKq3fj5/tDN4jjXks87Bpd58/6XoASawt9w3ds5ded25v0adKJR+jxtySMc60XKnZfn4FiND0FCKDQG06Vz4MxYg02wYGA1U4W/2hjKboVNLWywGCM3C6vyp337ewt/ahdffbrW/nMSHDYeZ5LAvVbLJSSW9XjmAauAbx0dvA9SiCrVTn2tPNeRhg+a2W1WcxK7CWT261Kudrl2WA8L0npdKQZQzMWvWPJSW4eT0akcDHF/PBAzmqJuR0Pr8vgoZZ6nQUlibKbYQTYSUyVffWGktOpit1MlIaN2KhAZ1cqAIt2RK03RRQgcIybHzzLTT0ipx6UHBSKbT4WAjW9nVa49s+eKsmOD4IBFdKn+aZOkPhbOH3zjoaIiaZHvWkmHIsejY0hxmmRj7enJca9UoNJ8wLi2e0P2l0gZ71fzFq6wV1dE3sTwthrNkxuhwNKh9bxTbhUuqES1Z8qlaSAe2fPU3532FRWKeahliuFJh+bwfjd2icM+6K9tDEhFaoHldDtpr+w7ppoVjfq6VOVoHZagyd3aUXJkEDB0qID2V1Watb0olU5HlVA/7zK+nYHO/co1lenZjpdbzeat/c1Gay/R+Ajo4XsLZlRLkLC9hvEt6o88T9Wg+pTUyY6qUrLLCIrt33porSdTmn5rJrpLaUF4U2v4lVolOcD2lOGlREqpRI2zXrlJJPJWVr1e9laBoHj1v7zjQKrJaTnVWIn7CNpXBOEDQnInh2r5olhvFBo7SVB368dKMceq0jXRBlkzl7late2UmEwo7Jmauw3BB5HXsAhncVeug3Gnh8yaUJyjTKyFnkbkqWNcGYTPpEyx+6VFjBj7ven9l+a2o50w5TMHi9lccBNkGi/qKIOTL0xTbOPj1bC+lRAaQN623qDmrzkAfdU60F9yVQA7VA6Mg0v9y7pyz3u7cYTY4pcU7j6Ld8pixYsif8jmE2H7N3I5a65cCVR379lTLTRF1FW8woTohcWeCW87Azi+1kZSd1mMSn+RAraSnNmNKYws4F0EDR55eDzHHuuSkU4ea2srjPOePUxpbCt7P6VdGjnq2Hq05obYePIAjJ/GVIJLoNSFXqzOcRsxwgoxYxufYMIbJ2EVPHMLYZ0/Q8iB5T4hOi8z1s2gg2DTDxi/tM/YgPCF2oL+me+qS4ZIxn6QQF2S7z+IMULXqZfJkhdwQPOBOoWfwKz7Y8vF7SqZnkI366gBpbYFnPXlCZGeuksaPWVK6gnZ/F1Ad7Cq3Tpc/tjwhl8IpfWW1Vz7zd4zVKrEO+oFiNakZkwkVhZ/6kaB57EOszWoGIUjIb0OOyOf+2UoRkX/lHsr91n7UVs6sZ7SzUtpwXMFDOR5oOMxlTljsptDDlC+CD+tj4ruKROdHKT9WEJaJnM73+O0RCn4L30UL2E/+vj3h+we+zpH1d5zYW2kl+9+DYry+rHOlNKbkFdOteBPjV7oJH9bj91Y9589TTE+RzX5/T7MbmKqjd5hYorN3zPUhs1HlBEGPGqfZkRPHevOgXtiBOXKan4MgZiIWtwl5MYEVNay3TWCMhf8SiHCTWqUg2c0gTKlEnXrRs44DrcSoV3G+Wys5NHJiF4d887g43UVhN8tsICKtFVmRJWXRr/PZXgKoFhNK4f8TznU1U4W/zqqqDMusfhAmnR9Vn7BLVOF5flJgNsHcz3cIodw1qcV8sl+ZOPWqv+Sqr8/7ra+kVX0METa/HsvWpNWchlGkvyF5WMaNQJ9TG+2VQ8I9xpBVQGMzpa7Jmq0i4221yplF6jPBbCs/Dcht2QmaZgJWpJdsrTpprfHOobXYDb4KKtbGk6J5thwMIpVac06VUUGNvai+hkCfijRj90RJEXbVyiE79i/+WseOL/6nCU+5GftTCWAgoLWo9Rb+CiqxzG1hcBJnZDuBc8rCljnlxsnCWeuLjygo05NQHSwCOGgrJ/hUe3aiWpownae/ifjEU3CidnTt3PVRavmtkBoq564cZgzYSEA1nIT8KCMFeJSFWSZz2H4WnryiY/1thw2QOXSsvQlGGuzEPuM/yFHkAOO4XVkr9nR2TP3EJUDBwHCZ9Ps5qQJpiW70mTNe1QHCscXTv7loQJ9mqA2Vt1vOo3ldR+ma1b237jfLYVskNf9SsA3bi3V+U5ajBsxWHyx+1TcV5Vq6iYPUN7+b5YTsxdt068YSYqskFV/DmfS+jT0At9JzZc7MLdSFgQWj6GK6FlycdVn08U5HYCV6jhOLP5MmPCwn/3730s0obLlVrXNnz/0oiRMn3a9DvLu+y04iCod/PMrgpVxXJcbJPp/YDB036EHOSP+lw/niTY6ck93ow4/G4PEhBmogBJeeLs5KWPgrdeoqSNft7KXkmjnRjVGHt8+SSHvKltExzVRZ/ZsfFQAWAn4wMDoWZfbbn3+JTeGrCt90zBmLce1VZW5mPsugX4UsqIAf+2qMk/rwgHAh14/UBkICUPZH1OgltWsezQRlgu5lO8Gt0v46yFG09xNfnyHq+iKmCZEfO6mtxkSOIMqhccczPhcUuMp/Ef2pB7ENc9gnLJs/WIdh6NTvIWdiBfYZ9eCXvs96aO8/gzMa4vDYicbSExaneWgt9/03CBLOxNjdeLNi4XGNRSaPELxDt/rEkvuLkoHzCV0kzlXW+6qXjbulPXyo08fJH0sLeQ4pqP7lGBtYLAbdAMDlDNI9F4CEr5h3Z7D3mlM+YaKTaGnR1qA9YhsN+DHWy5GqVvRWu3YMSfM3anouJK9G6WVaqLFljvWultb6xfTRclCScZeePdLsOHNG0UB1FobXL+Zi50jTJRt0eTYtjry6MqG30Yk6b+Ju3xB9A1eYEzmZ6wBaAKub0fv4FO7SLPLVQ6MTFhV/Tr0y8cU50z0zGV04Wq0ThaPF7qeproGz2bieChOD9e5vz61Oz4c20CizVMajll6h/PpXKCh+X6W/yYHccQDmFgfaKgfNFRQjvsjJqataX3GheMl/gSLNZyaIej5PtSOYIcuA/Y0NPc8L/Z3in5Gqw7skBjjyHlMHSV44sbL8+kv5NjbakoUgck1ZCIKM/Xi/EfiBTSPxfdA7tps5QAFW9XEtXgmVpj6YCbtPDu0ALQ0wQnYaU86EwwZQIabhzWFiwFxPaNdyhnblAKlei8njW/uqBOsMkAd+loWfv0QUvoVp8NGRqIX8eozfEa57vuO6fxYMj08kPCKHHDMdxC10IkE9jZRIn1jhNTIvNCbZXbht3lSMZYEfiRT6lHnZSjoWl8afIE3zeXekRhwn40lTOnNQCcgHNg7tUb25pfIIaScKQrBabWgAHVrs16gGlz7Mnv2wneXBCDqy3P10sZXV3hHHGov8ODQnZOiyxC/KYcKFolWFvNDDBdb8CGpZtO3+z/ebSULetEGMjj9LbS+mZyoExW+longq7YcyqL2RcsgXwQVWordiM6yt9BG7at3KHDGBKwFdjCFhYIz4fgpdtm4ll2zl+8sTWXLWGxZRbHHUZjexbJxWasIiW8vxRLfioC8Hz9Qybaw14lvNnbtn56kKluU543NsLucV6PTKsxaqjCfSs9fFFIuqGbTCXr5qC7JCxBT0XI/JNBJZwKKu7C67LIiD+5Pv2N3j9IYBOpeHaQJLRLvLs/sj3ojnFuETz5P98ZjVNOV0fUEPRElheJulla6ANdiXARjq8gZoZLmvItcW+R9bZSt7BXPZDEalWhEwy3xDGiMHIQzDDbWQvTIRq74REwNIGQnEMgv/JTifyPh72KdDyp6ECL49nygHYrmi3K63xA+8edb9iljbAP4QAPfy29HEUlrERrLeBEC3YOEbOoBNYCP3BYoxWwy8Y+UwGMssckxEj0HWnRujCA2GYJ4N8iq/bje+eDN/dmIRo4esGgDfndDMKCwu0OEu9u/JdjoD4xU8YYMuQ7u1ViZ8FVMJyAxRaLP+GlNgTuiXdgPzj6+wfG3xJhhysj92LNaYPhtrELymElFGrSsOvIg7y6hjxV40IAJgEJjntzrrx4yLwES+r8/GHrdNEVEi9Rog7exLYPN/DMgIy0YtklihnYDXwdhtBWtSpnbNR0NDrRrBBd5UTb9InV1QG/Ks8bzlQOLs9WJxDTYR3wTA+W8cEWATxwDYvGDKDT9+7jeHb1LvCQkDRHPkhKXrsjBliKrJ6l8/kmjm6F8l7h+A6/kKCa/KfLPrBi381fv9K4brNwxpbXz+ykU3Q382dOZh2eGLgDoNlwG+DvI6EjECyOkJTukwz35z6CaDc4NDHU6vEQSQ98dQF+1isPnA/uaO8BV7JIJEcoU92uy+M2s/nnVyQ5xQUQzGOSH35WFiVdjpj8camCpnkZP+SBCY7NGT1IC038zIw25yjiGF6NOPDEOWNpLDPDChW2TrldyAr8sOjoRzpCooRT1wqmlOk9M6nJUU70lqDkZbiCSYL/GY5gjbfKDQd2qJNoj6Km1GH15qZRtG1lNPWx6mmAT7bI5K74FgcrxYHT/BHNoNSehMC8i2G0w4EFBCJCpBOxpZZra84ehaiHbNz3bqZBIz2S4iqGwD73qx/ZGMByewKNilBLBTKHR+sGTAMKNwKy4XYpmQVGCl8kFMpEuj6Z6Vc/cUSoHzKrGBfVU6BEua8jMaFzQGBFvKz0FsFDdB9ytlmiMEGJE0w7bi1VKijhxDuuI4ZIMXUuZINGy+asj8oxo0TgxJFNJLKAEIVGcMdSAlfAvHSGeKR1F92mcK32mxQhnRFjZdQb7e3jKZQE9xmbC5l71satEYqWQSXfcDdtZousyJ04TOBZb6B4CtRhN018qZaU8ZT1lY0GBBsv8MzVuomafI83D7ofGlRS9qSctRtZ8KIxuaycg5xQpGRpiNtxYJRhoUeOynGlxyiVAYnRZUSCHOp6nJelKGAPEn7Q6ix4eSgLrtTGT5uIrajOtKbtw9ubGC2lygP5UIY8eS7Nxp/jghNXXpWEibXVpHDvsHY9C45NjRIAoMjHowdVDIcUklQiNmi5LToZkPRpynKEkmQl7oUnRsSSbieHZJLtYupg6q35nV58ZzA0PAkrUKlN+nr560W+EG05AHY9FO+mAWlI5hAWQUj9ZMvo6J2U9cZV19rpEmNshphyYcvmUiOLYGPxNsm4Nnz7Hj6nssfNJgek7ZiE+sV+VEmW3Oo8U8XynR3G8OFuF1kpyKYT3YUqWrI83ZRBhq+47E0iyeCW12uPNaSyseRIuVzGe4brQt7h8Ns7gyZu6q3JzhCtq578zHQpon5MkWb/0PFYnaDAmkZ2+kaUsyii2/lWm5VQArzgoiD3R6ZMIDFlzhNXkn0Rr1vCof72l/G7vysGdjWIEF22PZh5JDrv0gePqWgbW9HEcmivhkAoOxlHO+nqg5ygFlYmcYdjP8tL++KdxM0rmdT3xcM4MAtL1H744qdcPLFqR74c3zmYpDyydeRaMlgw+or1/5G+XtZGA1ghSRgfKLmB8jcWN+fGLRR2PHxE80KXNgaDZ+/t9EH6Pf4LitJ6s0DdOI5xSBS0IQMYktrOQ3YcUEcOKRR4EQlkpiJPb982soJATJmNRlIGpia34F/dyGqzaRF7+J1aN34lZx+PwKp8AnBUA2kYa/oi88CYXG44u6dY1vFQBiCPklKtiOCXwmBVLCk28EZh8Gsbc35dhQOgxX6lNVbyfC+tf4LelITtfeb97t1PGN4xzzVuPMJfbUAPiRmNdfY7gkwCsd2DPtO2JZZfNibV35eismd5aVRZSs++R92xPFq+klNNYrbS+Rmmld+pVJLHEG5w01kctse6VQYmzEu4WNkgiGfjLu43dn3MdJtm9sSQbjJDcFSUpESdUwgGiIk3ojracBNeJfRnnCQnenXEZxvCFH01Ado1F2yR+/KUFY41aO4rsZfOTmuissJ816R3SY/i7RXHdFzWe4DbC7DMEB9LFSTDgV8GOkqsKWURIaBIy1yHKgSzUiGEm/0rFCK9In+ydxdJQ69cDYzGTQO+NXMuRoKpY6L8qu4mDk1s69xHFUvE5Gm08Dupzn0StvSPeGESUS2J1RK5V3F2WNXVcya1gfnjdPl4/nVmHF86GeKUI+ySb41kexadbZsi6e3azb7renTV+JuNpZckie1TtRtysl9N+7JAiQYYR3ismR3wAEIohR2EcW1oAhSekpgGRO+8vxeFc78jHQpU9Wmim8nPTltHLlGJOeOJj0Zo1yMO1yK92pOKQHCvkxdQM1C8wzpWHcK+ulEhGkfKSE5WUJcfyPvVi+V2Nc2c0cfwOAobR138l1LRcmBzl/kHR/A7yQTd9y3RMLnLJUcmWZ/itTZcYtrzmrcBHYQORq5jhDQQRaL01MAkt8dVPdOktHeshYXbd5yFgIEztlLEJCFK0kvF5p0dTRr1bO7PC2lvs3UD9XykeRWulNjNSd7kTxo12r+bUQn8yLvaNvMDpekmb0vCTMSJF33jw2mzgdCW+kdsqdYnYqhWNSa0KMKcTKYyoWtlkDJ1wzD3ndHmAVUvyMVqI9DaPtKnlRIFGm7MvI7759xtEs28jvzjfutGtbwb7TtbzgGuu3b+f+S0WN0/5S23IrpeREBWl1Azc06pYTHHj6H/CAGTqMd3M4a+ApCGP7FX1BgMmvqL7hbOCJGOnFQKkqP0W6b37Fj8yeb0uvSt/FWm+ediNcgNOrYkADladE/8N7ycp0vMA+9CUIt5nZAyya7oN+//lMzlV2cVBvktvYpS1ts5EaqfqKatRIUKnz+g3s39DonD6ClZq+OEdVfaPqVcSNcVn6eXCnLT00mPW1ZzQiobbenansZaj0wexh7PJ53yJprUenfKMVDekYBCxH7M/+i8Pe6fhHZst4azwFCULAEn1awQeWc7W0U1wFGtB0YSz2Squhtuhp6kkjgXHzaV4HYJ/l4PdlrNcEMSqMu76LmeQkCKFsIA1ZdNWtP2XUaVoS8n6gOG9LHxa+uAVFatuR551Cq+YFGaDs2QvMl5cPrTKUeE+AtpOmGcQLRLh5qFKxXzS/GjpQKa1RtodFePb3bc6BdmPfarHNS414a6+QlrOcdmH7jGQtDdvaXXddg/SmTlkrMZ1UirFJDyx3t3dE7vatZXaWJX/nrM35prCcueY4HHda/EHYJcjkucrAyEqngZHV916UIAJN0+Sv9zbcua/G89bo/a3ReZsXCGCINLD+IbUqxP7O/QzyTwpHfEz2D7j3dgWH/fOcB/PNcpzBXT7PWa10e7rq/ObX8HlW3Tnfulien5cy5DcAa+UcAMLIlsVLJqVe7/wRvp9z2lbZRo1V2FLMSxDhJa940vQdhPpUueucNJBHqkyl3vOhYTWYxnjrsjKevIu+cFI0JUMwgcr6fQwGWm0f9u3plbi1E6ysD3esRH+N1Os1QMdswHGeGFreD8X6pePvSevxgxjAjHE7QFqr04r8TY6Ql+zAne6efCXaTI6AIJG3SsWMZN7Fjuq7Rn+nr/Gmbivemu1dN/qmXJbOZl7s6fzGFSfDS3pibq5a96u9q3i5in5XzKh16XzOMH6BJy9hGGkEz/X8t8ZKBkB8q9w96huO7UpuPGtPg4PN/dbcg0/VTdM7cG7vKchyOUNMtl6pmr9vjWjMv1FmT5m1Vw7xhoa33FfBNa9WIJFIq5UfUJBTZLqA4N4pnN7KjByOUfY7v3w4zprbwOtqbptvdc4ttZBbq+VaqbgN5Sfv77pPvsKQ4sZBq8hLliAA6iOt57yg6DhV2zkrO2nekOWpuNOK4R4P31p6gfbrDtr4s9KS+6RTBm1PPw2h33oUNvxv180KklGpvLczzHILSnV7KV567oBAalWXRLbStXQ6Mgpr6ZVy6uZJUp0JJ+FOwo/oLmVHVufWHC2w+q10dKlXsTu9pguCph7mPmzVoIar/SSl0XX1lJAvPbolyT2XO30wul7uWjitoqfI7GFLXOVN8aDjTckTHwKjN7Wdp87c8fCt2gmue+4Ntue7gZ6n507EeJk5d8tqj3vrKvLibSP7ziMO4UpiEqJSMg9uKiniYMoNf/0d8PZ3HPLLCaK4xaNJTGbCqu6EOvDlAlHcXgkxqud4fWz8gUXpIvJ8SfwgRU8lvOtkLduJwpGYLUld5vSrBpcNAsfhXXsZSB58wese/LDDJEVVQK0r/ViguiCGD8xiL3UnzFo/742BveYmv3H+UhG9IQ9dhiBR886Ic66KMeD8zrgwyzD8KLPKMebFclwA6LUxGJS95OahV6pRWZirOpo53nlzzwrtNoGV6xaUdqM1jrwD6gYxPTjdAlcYnIlsJ7rB9kNCgV/de1Ri3eUMXeUefW+5eX7ydp1M7XeTVGpXE9not1iJKgVs9k5FjPlX0ESxy3t7LoecbOh2PKkQ1UqM+y/1/Lw38pyfvIWn/dVtdv0vb+faxcwrCDe7J0tke+Z3n1Yp4iFvVQDiPO6dCmVNzjuOL3GUiFNcZcTxDciHh5YoP3y7BPmxl5cnJ/J7sowFU+LyBo9B1GcOYrGIVmRCudeFqdt+5/G6Fnq9a/4wBrOmGntjny6Pysz6fDf79VWk8IoltwyjwPGRCbYeI3zgzJpR2M2rXCpOgxYGDStX84PaU1x8MB4uwjFnpdjhUimRrFdGcQdwcHc5UPLrUBwUq+rhN29dutUzcrnkz5Zf70FUMwGxXwvHcgkyqroRzMRu5zaP6+7WrLUyDqdVAsaXMfZPHg1U8du4fwnUySCd27ghl2hkMP+dNwLsKsM5MoezZrgDNGdUOJvXmQH2swxRV/mKTnfjuHJzNC5cvA2ZbCOxBCBqbyPRlfLAa7qyd51iA9dPcu0ksyJK35bnlYTam7nYdw3zvIXBW/kJNDgksz/VQZg4TF+lDT5lbLVXu6lOGYiNdGwCRzWAeqyeSGReYGYt3KXIDA2vDozvD5HxB9JILIdXxuAdn97mMoQRJKTD+3bgm92rV7pMPwt3L5rBce63Et/U8M3gd/dut+2Fc6jBxoyjUxjIPlO9Vq/LwkANjD1XE61gd4BW+QrQ8RZ59r6CWuoLZ9uY46UtV2IOUss1MBZl2Ls70I8B/mFAFwoojBFona4Yg5R5ZRD3TphXaunHbz05QDXG5sV3NS1b3JXh+wnkiq839WTR/bvZMq9oeSY4rOH3Qfs2ohl1PRNEyBLx6vzgi3BaQOiuRD924QhinZd46J2AQoHRy9BTRioeGvTAHLkzE9nIJ0ZLqC5QDPnUaoVInhn4uvXx2w5G+8bNmOJ6scJMQ1jB2vY6IDOB0U+igYfe+p5Q6WmUsS75J8+X0GETRjXdS+OVmqcQ5/Dzhq125z0jYqZNiIjE4W2AET51Q3x2Qa65vmLsOyO1h0FveOLvuvfCa1eIssoc7IJeArC6vvl89ewMpfIeJmhb5vRWHWtNHIBRqkK3w85ZnQdhkMFeO8fV8Hw/T1KkYXzZubIdIiP9aMORn3caPNnDTFTImddVcYVDdl7o/coArBxge4csaL5VLa8xwQFvZC2I9oyFijKjwtEGB9aESyAy4M4oimHwWcejfzKQq58ae16kcirkgktXjcbA8NqNpsTWybo3g0IM5+yGu2Qcj6F0WHgv6fzzJjKiJXPazAsHvIjq2hnjomBiPBByCfE9wVNwpd95p4F3n1z61G1wZFjbRZiU7RCSxepcSw9tpMNzS+TR0gOtBcHrNzR3Q7KQmIyWI1zW0Dqt4yYIRbJ9wssyETng7flgKBM8iX+IAfkVqPDMil6xAECSboEcXRl7y1rxcSN8B7EweaepUaw69zMEOCOAOd08jb+0H8Feke0O16QOXBHIiP7SV807nNnPOTrHUS64yMn8oAboIQAJQOAxm0AouKMJwR/nAKIwYASEfO6hQTMgduuha3ESnpFRaw8QBb7XpyvHnYhsEnSCfG4xGomxiDBRQnFigwCIYMkPsTXBQH1G/UPcUzAM3CGgK45hadwpSwDdlc8w8oF7AT4BVyMC0d8jY1PBI/iMHQCaljBQ/EfeUetCwfAOV9cu/PZAyvilfyWKAhGI7W38W1DZmyET9mqsW1Tu222Lxg4kBJ6Lg5ogPYYGe+YwbIO64r4/ECyhHoF7wquAFTPibD/bEKa4IZj33B3GFMQQuSkETwMwbgKREFQJWkKQxb2HYIt/hJsuOLxTyM3lrV1gcPBrx0093vSV+UcvBRdi4BGhHg5wrmCIoNOPKIKFwHzp64AncV0SgjT+GuzhxG6BTgj87AcLOE51w+dCsPQZ2xkGGl6IHE+Md+mai3qGwKXAjO/IgLkLQfm41Ni4CeZbxlrSzhaygy0dn5TBfj6HwYv5TIEelyU2VDxczAOX/3APRbA2LzjL53SrTyI3g29xKxfrOz1lkc/JD1WFe7uhJ/6O+Z640IJqgztgK4JJgIAh6oEJ8hn1wUkQ5IZ0iHcpSLUeL9g1FJQgoXw+gpyQK1lHoiHCIvshLIz1GgKuoh1i7mL+iSliHrnDg2i6fLZsP44y32OewFkQuQmOgiNhv4NgE8kARiefMQ/AWlqNm4vkCMO9uCwu4TlLKM/lPoAkIsDuvDlucpMcu+oDzCKqcmsDTXlFQ3QBsARDf/IyCAEf0ZVx8kIbYqC4Esb3hxu0V151JLrDRcvQ/hidt+NtpnPmZYPeswwzEGzCzvGeJ46agJRMzLz1LXNYDW8Hm1z/TQ6hdPjlnVgvhguxMq/eCDnMq846N4NfXnkQcXFetRanF3FFpAe2il98d91bJGNhvOjCCDPvb0PzP+91a976AvPIdmYlYE5AC7qhb/ZZi0xdaCcYRw6961I87wRJNpwX+TVvmDIGbufdfN5M5rUpjOsxPi0vOuLaEO6FSNCPt/t583owX/aK4XvwAuSMD9TD+9knJIslX4iAH2TW2AzD+woebksgPgTFn3iLXuEawCN+BOURdKXVVuhTGrr1Qugvp296B9x0Xhl80r2NObilUyk5MV6edGZzO4OoN1TSpvXhzrMOvv2naRDZ6ycvgzRxV4MnfVMZHtuE9SVSPqNZfaUxDdd1Xs/cFHfwufx0Qfej4klxPYuvYHn6STNHun2fJLm/Tiia9TCIMBzzCdPcGfD5C3o0EV/5NH7QUIPX8atw+4vUi95iDCZ+bi6QHwp/Akeb0ZXy6xQfkfrygvSUEN/wSiVGb3n6GV7ptLNlQhmX0pRYU27WGFPRI+Mqea+e3X7qAr4MoaTjXsJ4Z9wk8nnQRAJ0Dah80ifv71hDBUxOEbJ1TAhKuvl67OMI0V6oB4r3PE+KqMP24vAyjsgnwozvGcrJeyYMGkzYbXzXQEzKr8vvcV2PYbJOeNRDWVjQ0GO0Kdf8M0+QFDQOw2ulCEvB2u/F1A/nLcoRAxr10GJ4z/0t5HPPSz4vFQ3DbUNMCn6tr16VJGg+F52hLnCPPKDjXvGzwxDLZhgvV8WmthXjWenN55ImtIuJYhXjNDYzxjlFCPJ7qYKhEU7ChG9A1jFe9Th+Z+glvAoFL5/DeTB/Xep7PqGRRC06X0u8ANdGgdW2P3HMhjGd/IMCcaQ7+0tYcl+Cu7nHD2i472sebb9lmB6Bt3yX2wUpn88r54WwZBRRaGzICOiYXebDvshQ1A55iXW3PGT63s4L95TEXX4flEIgbkZtxrx1EeGEQ/OecOeMr+3CwePZaz1AO7CP+xECzv2LqG5cOOI6zgRw+2SdYYP3k+Xi/FnvHrm/N79XPlvur9QkOSdXKolP4ja4ccQrgs+TijMBnHl5aUbugqefXn8azzuf2rWH641hbGpyvjPfp/aojMYFz6G2PFxXnzPDub1imfXzougrlXsCArqWqXyC3pdpPT95/fJKbRc+gV0H1R09jXXSVPKkWrxLTyZy2wuSS5NGe88/CfjxEtRXU+c3/I7xEv/MPvJSlcf1xjZoPwgH6F6T9MNF0ye3I7uVe2u3NgvGjJyUJghrhkLhPvkdqZonPn8VcN8I99+WS0mUI0c6wHz5jC5BMqXdxiyvF7D/k/i8xyX+PWmG+DX8fSQP0P1c0QCwWSObrgTvSApOckwdQRm8/evWF5rraH7bU89pDDc8wtjpUWHAwH3yL5YyqIOtnbCFnyno46mQ5yujaYfBJARqQkiPMZXE/wxs30ZQGq4SyhK/Qg96fJx8p33p8tdan4K2YLO6FSSWTGgbP8pi5e9h5BCmgLV3xrVubw2gjScBMEa9zop6nd6VY3gpFmNNWwBg0JoJG/LfICpi93mfj+8xbhB+w5FbHr2tgY8jiX2Pow8wpxvtekkaAMz4myNKuOnZWe5JuQ94jPAmSDlwCkjHSYMfrA3rHjCpDYnH0wjJAZDQbvuBzdDfyJE42WM8XvnEDQy4XmMavOJpQ5Iy4pL7LLDXYnLa/iPG0SHrFVUcCfyyV4qamgexXx5v83ZcTQund/elDZXxSQKeemaYq/N+anXQuKfTIMgI5dTJ0Bl8IREyFBy4ECkgDq7Q0RvdDJM79hhoTB/phe0FROhazfsnTe3BXK58PwqUMAQiPDJ14AUCXPibnSvhI9xHEOG1+UQzudKNjQLEzA1nMJg5oJCdigOhiqMCQ/HGMfODGZzV/jz+1Q8rgRbDeGC25hOLGCszjQNd3rwNmGgKOYrvCyRCgerCUVCs8t+AhuAV/qbD/wIiIvDe9bzyfVAWFFR89tygyLjwZOHQJpIbGMayva4hANf3Eq40/XMgIBlLOMDjXwPxPW7Q4vfW5B/HGNBazKdQKn6fBLtgqKCfeLSYX1EAQZn2TvDQ1o0e9fRMX9bLfwNKN/EuoAqGEH5jGMHTQVAIDhOCT4E8mY8Npic4SM9B9B9oM/NC+Afrxx1EQBYozzzftY6gJQABGCR783s5TkNLbe/Yf0DT7J+74Cb8IYH9wGeLLUjYTdQHUtLT0OOfGgEYweBTAJ+7vNHGhPL+yXJifLFdifDA9rT0KxEThN+b//fAC0f8Mh5E4oB4YvPCp5c+ubCF4aHCprbSiaYfbmGre/TQaXHMhG5B2RwutZHX9N3SVPzYSvzlXnzdbl/DqXTJPa83T+iSWKj5JvCW+ioLfxMVeyeKtWfbidN686JCIqxY9tR6ssa324VH0ko98KvUkgCQz3ggqSp/S5JKW1XvWy7mRMvSRqLFmO5EIeVbIodPduIBZXQ/haMwB9/eWW+i/r3P+gST3cmBrf7NP4TxD9T4S6k7oWZ2LmHOvbqAIfZO0Bne3fMUCDr/b9Flyg5mc1/tyjTyPDly/27G/0ACXUW1aun+vGW/yE73k4yCP2fUk4naznG7k+Hd/tlC+m2b20YfT+6AmbONSs26gJu+i5DTrqr2lfYBf/NdnyvzY98cGEj24wtD4l8o8cuQLzgDhgcZf6Y6HX9SB6O9ke3op39gQXlkW9qF0T3ZDhB4GGG2+8W+FEfnQywO3yc6h3+OBKFLvZBj84lxFtsQ5m3shBf9fLR70l61833cj3F87lyOZ13O48Muw0Tdl+MACk//2PH8qxLHj79UInzw6GxgO8eAqsGAe3GiBAuxcZ4Kfs5949r3crSbg2/a7Ya/WOQg9EdJb12V2Dn1ut79t0zu6jwZgz3slc740wpCeBJU2OygEYb+81N1LP9X8oyWUcenV/Saf0nIv/mcVv+7mIknFyYxZuKjAM0Zb+Km7omh8h9Cb7dphXqIEiAU4s57sJ7/JfaLeds9AxTFChxGarA67m9z3uqMwgalj3ddKibBInjeWSXA3iMoLc0o+pkdO6vVWoCccnX2U9Mycsd6gRlbxijNTDyz5plwSIB2gDCON5mx/73PhYnKizZ65bAEAttCiM95zgn/YrmLBJdLXCdrgYe11nAJuLCEbwGjAgjvP0FyueMBouShMCfogn8Nicrouod1LzvWiCFJIH3PnYBs5x/Eds+CtyrcOeQmjTyVUI+RfnjrBSgTNYBTqA3WAjuTlFqDk+gLLFCtIFb9RbFJvR2pODGtVCMxa5noeWlG5swjryTwLpFjDNA7Frh8Q9wz1yaJbOSuSkFhmH+E3qG/C9izZcbVBe16m0tdmsGtykIBuXRNKDf/buHNF6+kRvBbIskzQeRfq0tFMO8LaJyIG4YRAp68jIY8iXtXMjPW8LwJZCX/4PK9n2V5XQpRmj3FSMMCvRpFAY55Xt7dUHc1eT0E2A/ByFAxMZyrFex2XYUpV97LC6LuROlyf6Egc0FLl3fXFKSWlp1eQAVOJncKCCRcyjs7LyAQosW/UQkWywQ0Af60a2ObuGXaRvMlfxHe6Y665dtXBqV5PImnlbIBHJWkgCk9VwX0efT2u3vBSLj58fB4QOK2h0rEtJwMbZ1JvhCu8y9Td50mxGhJHOvlf62CbchEDCcPY57K/wD5+QrQ"""


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


# --- chart types (taxonomy beyond flow/arch/seq/schema/bar/line/scatter/geo) ---

CHART_ALIAS = {
    "container": "arch",
    "component": "arch",
    "process": "seq",
    "flowsheet": "flow",
    "decision": "flow",
    "point": "geo",
}

_CHART_BLURB = {
    "bubble": "CSV x, y, size. Dot area follows size.",
    "beeswarm": "CSV cat, val. One dot per row, packed so dots do not stack.",
    "step": "CSV x, y, optional group. Piecewise-constant line.",
    "slope": "CSV cat, a, b. A line from the first state to the second.",
    "bump": "CSV x, name, rank. Rank 1 is the top.",
    "ridgeline": "CSV group, val. One small histogram per group.",
    "stack": "CSV cat, group, val. Stacked bars.",
    "dumbbell": "CSV cat, a, b. A line between two values.",
    "waterfall": "CSV cat, val, in order. A row named total is a full bar.",
    "histogram": "CSV val. Bins chosen from the count.",
    "box": "CSV group, val. Quartiles and whiskers.",
    "violin": "CSV group, val. Quartiles plus a density.",
    "strip": "CSV group, val. Every row as a dot.",
    "pie": "CSV cat, val. At most 8 slices.",
    "donut": "CSV cat, val. Same as pie, with a hole.",
    "waffle": "CSV cat, val. One hundred cells.",
    "treemap": "CSV name, parent, val. Area follows val.",
    "icicle": "CSV name, parent, val. Children split the parent.",
    "sunburst": "CSV name, parent, val. The same split, in rings.",
    "heatmap": "CSV x, y, val. Cell color follows val.",
    "calendar": "CSV date, val. Weeks across, weekdays down.",
    "radar": "CSV axis, series, val. At most 8 axes.",
    "polar": "CSV cat, val. Angle is the category.",
    "candle": "CSV x, open, high, low, close.",
    "status": "CSV row, col, state. ok, warn, down, or other.",
    "forest": "CSV cat, est, lo, hi. Estimate and interval.",
    "qq": "CSV val. Sample against a normal quantile.",
    "volcano": "CSV x, y, label. y is a p-value when it is at most 1.",
    "sankey": "CSV src, dst, val. Width follows val.",
    "stream": "CSV x, group, val. Stacked, centered.",
    "funnel": "CSV cat, val, in the order given.",
    "combo": "CSV x, bar, line. Bars on the left scale, line on the right.",
    "quadrant": "CSV x, y, label. Crosshairs at the medians.",
    "contour": "CSV x, y, z. Isolines of a binned grid.",
    "math": "JSON equations, or a text file with one equation per line. y=f(x), x=f(y), (x(t), y(t)), f(x,y)=0, y<f(x). sin cos tan asin acos atan sqrt abs floor ceil round sign ln log exp min max. log is base 10, ln is natural. pi, e, tau. ^ is power. 2x and 2sin(x) multiply. \\sin and \\frac{a}{b} are accepted. xmin xmax ymin ymax, equal keeps a circle round. At most 8 equations. No 3D, no vector fields.",
    "dag": "JSON nodes[{id,name}] and edges[{from,to}]. Longest-path layers.",
    "force": "JSON nodes and edges. A short deterministic layout.",
    "radial": "JSON nodes and edges. The busiest node, or root, sits in the middle.",
    "tree": "JSON nodes[{id,name,parent}].",
    "dtree": "JSON nodes[{id,name,parent}] and optional edge label.",
    "nested": "JSON nodes[{id,name,parent}]. Boxes inside boxes.",
    "kg": "JSON nodes[{id,name,kind}] and edges. Same layout as force, colored by kind.",
    "context": "JSON nodes[{id,name,kind:person|system}] and edges. C4 context.",
    "uml": "JSON nodes[{id,name,attrs,methods}] and edges[{from,to,kind:inherit|assoc}]. At most 7 classes.",
    "deploy": "JSON zones[{id,name,nodes:[{id,name}]}]. At most 3 zones.",
    "layers": "JSON layers[{name,sub}]. At most 8 bands.",
    "integration": "JSON nodes[{id,name,col:source|core|consumer}] and edges.",
    "current": "JSON nodes[{id,name,group}]. One column per group.",
    "er": "JSON entities[{id,name,attrs:[{name,key}]}] and relations[{from,to,from_card,to_card}].",
    "wardley": "JSON nodes[{id,name,visibility,evolution}] on 0..1, optional edges.",
    "swim": "JSON lanes[{id,name}], nodes[{id,name,lane}], edges.",
    "state": "JSON nodes[{id,name}] and edges[{from,to,label}].",
    "bpmn": "JSON nodes[{id,name,shape:event|task|gateway}] and edges.",
    "fishbone": "JSON problem, ribs[{name,causes[]}]. At most 6 ribs.",
    "flywheel": "JSON hub, nodes[{name}].",
    "kanban": "JSON columns[{name,cards:[{name,blocked}]}].",
    "gantt": "JSON tasks[{name,start,end}]. Dates or numbers.",
    "timeline": "JSON events[{name,at}].",
    "journey": "JSON stages[{name,score,note}]. Score is 0..5.",
    "story": "JSON backbone[], releases[{name,stories[]}].",
    "org": "JSON nodes[{id,name,parent,sub}].",
    "venn": "JSON sets[{name,size}] (2 or 3) and overlap {ab,bc,ac,abc} or a number.",
    "choropleth": "GeoJSON polygons. Color follows properties.value, or --val.",
    "heatgeo": "CSV lat, lon, val. Binned on the coastline.",
    "od": "CSV lon, lat, lon2, lat2, val. Arcs on the coastline.",
    "cluster": "CSV lat, lon. Nearby points become one dot.",
    "container": "C4 container. Same drawing as arch.",
    "component": "C4 component. Same drawing as arch.",
    "process": "Runtime sequence. Same drawing as seq.",
    "flowsheet": "Process flow. Same drawing as flow.",
    "decision": "Decision flow. Same drawing as flow.",
    "point": "Point map. Same drawing as geo.",
    "terrain": "Not drawn. A DEM raster is outside this library. Use contour for a z grid.",
    "print": "Not a separate drawing. geo, then export --to pdf.",
}


def _chart_meta():
    out = {}
    for name, text in _CHART_BLURB.items():
        out[name] = {
            "input": text,
            "writes": f"py graph.py chart {name} SRC -o OUT.html",
            "rules": ["title and subtitle are drawn on the figure",
                      "JSON specs may set budget false to lift a count cap"],
            "example": f"py graph.py chart {name} SRC -o out/{name}.html",
        }
    return out


def _load_input(path):
    if str(path).lower().endswith(".json"):
        with open(path, encoding="utf-8") as f:
            return json.load(f), []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return None, list(reader)


def _pick(rows, explicit, aliases):
    cols = list(rows[0].keys()) if rows else []
    if explicit:
        if explicit not in cols:
            raise SystemExit(f"column '{explicit}' not in {cols}")
        return explicit
    low = {c.lower(): c for c in cols}
    for alias in aliases:
        if alias in low:
            return low[alias]
    return None


def _f(row, col):
    return float(row[col])


def _cap(spec, n, cap, what, unbounded=False):
    if unbounded or (isinstance(spec, dict) and spec.get("budget") is False):
        return
    if n > cap:
        raise SystemExit(f"{n} {what} > {cap}. Split the figure, or set budget false.")


def _fig_open(t, title, sub, W, H):
    head, hh = figure_heading(t, title, sub, x=28)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" role="img" viewBox="0 0 {W} {H}" width="{W}">'
        f'<title>{esc(title or "chart")}</title>',
        f'<desc>{esc(sub or title or "chart")}</desc>',
        f'<rect width="{W}" height="{H}" fill="{t["paper"]}"/>',
    ]
    parts.extend(head)
    return parts, hh


def _fig_close(parts, t, W, H, foot):
    parts.append(
        f'<text x="28" y="{H - 16}" font-size="11" font-family="{FONT}" fill="{t["muted"]}">{esc(foot)}</text>')
    parts.append("</svg>")
    return "\n".join(parts), W, H


def _mix(h1, h2, u):
    u = max(0.0, min(1.0, u))

    def p(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

    a, b = p(h1), p(h2)
    c = tuple(int(a[i] + (b[i] - a[i]) * u) for i in range(3))
    return "#{:02x}{:02x}{:02x}".format(*c)


def _heat_color(t, u):
    u = max(0.0, min(1.0, u))
    if u < 0.5:
        return _mix("#d6dde8", t["link"], u / 0.5)
    return _mix(t["link"], t["accent"], (u - 0.5) / 0.5)


def _axes(parts, t, ox, oy, pw, ph, xt, yt, grid):
    spanx = (xt[-1] - xt[0]) or 1
    spany = (yt[-1] - yt[0]) or 1

    def X(v):
        return ox + (v - xt[0]) / spanx * pw

    def Y(v):
        return oy + ph - (v - yt[0]) / spany * ph

    parts.append(f'<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    parts.append(f'<line x1="{ox}" y1="{oy + ph}" x2="{ox + pw}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    for v in yt:
        y = Y(v)
        if grid:
            parts.append(f'<line x1="{ox}" y1="{y:.1f}" x2="{ox + pw}" y2="{y:.1f}" stroke="{t["rule"]}" stroke-width="1"/>')
        parts.append(
            f'<text x="{ox - 8}" y="{y + 3:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">{fmt_tick(v)}</text>')
    for v in xt:
        x = X(v)
        if grid:
            parts.append(f'<line x1="{x:.1f}" y1="{oy}" x2="{x:.1f}" y2="{oy + ph}" stroke="{t["rule"]}" stroke-width="1"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{oy + ph + 16}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="middle">{fmt_tick(v)}</text>')
    return X, Y


def _cat_axis(parts, t, labels, ox, oy, pw, ph, horizontal=False):
    n = max(1, len(labels))
    coords = []
    if horizontal:
        for i, lab in enumerate(labels):
            y = oy + (i + 0.5) * ph / n
            coords.append(y)
            parts.append(
                f'<text x="{ox - 8}" y="{y + 3:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="end">{esc(lab)}</text>')
        parts.append(f'<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    else:
        for i, lab in enumerate(labels):
            x = ox + (i + 0.5) * pw / n
            coords.append(x)
            parts.append(
                f'<text x="{x:.1f}" y="{oy + ph + 16}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(lab)}</text>')
        parts.append(f'<line x1="{ox}" y1="{oy + ph}" x2="{ox + pw}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    return coords


def _tree_index(rows_or_nodes, name_key="name", parent_key="parent"):
    nodes = []
    for row in rows_or_nodes:
        if isinstance(row, dict) and name_key in row:
            nodes.append(row)
    by_name = {}
    for row in nodes:
        name = str(row.get(name_key) or row.get("id") or "")
        parent = str(row.get(parent_key) or "")
        try:
            val = float(row.get("val") or row.get("value") or 0)
        except (TypeError, ValueError):
            val = 0
        by_name[name] = {"name": name, "parent": parent, "val": val, "children": [], "raw": row}
    for node in by_name.values():
        parent = by_name.get(node["parent"])
        if parent is not None and parent is not node:
            parent["children"].append(node)
    roots = [n for n in by_name.values() if n["parent"] not in by_name or n["parent"] == ""]

    def roll(node):
        if node["children"]:
            node["val"] = sum(roll(c) for c in node["children"]) or node["val"] or 1
        elif node["val"] <= 0:
            node["val"] = 1
        return node["val"]

    for root in roots:
        roll(root)
    return roots


def _partition(items, x, y, w, h, vert=True):
    items = [(k, v) for k, v in items if v > 0]
    if not items:
        return []
    if len(items) == 1 or w < 4 or h < 4:
        return [(items[0][0], x, y, max(w, 0), max(h, 0))]
    total = sum(v for _, v in items) or 1
    half = total / 2
    acc, i = 0, 0
    while i < len(items) - 1 and acc + items[i][1] <= half:
        acc += items[i][1]
        i += 1
    if i == 0:
        i, acc = 1, items[0][1]
    left, right = items[:i], items[i:]
    if not right:
        return [(items[0][0], x, y, w, h)]
    if vert:
        lw = w * acc / total
        return _partition(left, x, y, lw, h, False) + _partition(right, x + lw, y, w - lw, h, False)
    lh = h * acc / total
    return _partition(left, x, y, w, lh, True) + _partition(right, x, y + lh, w, h - lh, True)


def _annulus(cx, cy, r0, r1, a0, a1):
    import math
    large = 1 if (a1 - a0) > math.pi else 0

    def pt(r, a):
        return cx + r * math.cos(a), cy + r * math.sin(a)

    x0, y0 = pt(r1, a0)
    x1, y1 = pt(r1, a1)
    x2, y2 = pt(r0, a1)
    x3, y3 = pt(r0, a0)
    return (f"M {x0:.1f} {y0:.1f} A {r1:.1f} {r1:.1f} 0 {large} 1 {x1:.1f} {y1:.1f} "
            f"L {x2:.1f} {y2:.1f} A {r0:.1f} {r0:.1f} 0 {large} 0 {x3:.1f} {y3:.1f} Z")


def _ninv(p):
    import math
    p = min(max(p, 1e-6), 1 - 1e-6)
    lo, hi = -8.0, 8.0
    for _ in range(48):
        mid = (lo + hi) / 2
        cdf = 0.5 * (1 + math.erf(mid / math.sqrt(2)))
        if cdf < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _layers_of(nodes, edges):
    from collections import defaultdict
    ids = [n.get("id") for n in nodes]
    indeg = {i: 0 for i in ids}
    out = defaultdict(list)
    for e in edges:
        if e.get("from") in indeg and e.get("to") in indeg:
            indeg[e["to"]] += 1
            out[e["from"]].append(e["to"])
    rank = {i: 0 for i in ids}
    ready = [i for i in ids if indeg[i] == 0] or list(ids)
    seen = set()
    while ready:
        cur = ready.pop(0)
        if cur in seen:
            continue
        seen.add(cur)
        for nxt in out[cur]:
            rank[nxt] = max(rank[nxt], rank[cur] + 1)
            indeg[nxt] -= 1
            if indeg[nxt] <= 0:
                ready.append(nxt)
    for i in ids:
        if i not in seen:
            rank[i] = max(rank.values(), default=0) + 1
    return rank


def _place_layers(nodes, rank, W, top, gap_y=120):
    from collections import defaultdict
    rows = defaultdict(list)
    for n in nodes:
        rows[rank[n["id"]]].append(n)
    pos = {}
    for key in sorted(rows):
        row = rows[key]
        for j, n in enumerate(row):
            x = W * (j + 1) / (len(row) + 1)
            y = top + key * gap_y
            pos[n["id"]] = (x, y, n)
    return pos


def _draw_links(parts, t, pos, edges):
    ports = assign_ports(pos, edges)
    for i, e in enumerate(edges):
        if i not in ports:
            continue
        x1, y1, s1, x2, y2, s2 = ports[i]
        d, lx, ly, vertical = route_edge(x1, y1, s1, x2, y2, s2)
        if not d:
            continue
        col = t["link"] if str(e.get("proto", "")).startswith("http") else t["muted"]
        parts.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="1.6" marker-end="url(#a)"/>')
        parts.append(_tail(x1, y1, s1, col))
        if e.get("label"):
            parts.append(arrow_label(t, lx, ly, str(e["label"]).upper(), vertical=vertical))


def _map_stage(t, title, subtitle, samples, width=760):
    import math
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
    minlon, maxlon = minlon - pad_x, maxlon + pad_x
    minlat, maxlat = minlat - pad_y, maxlat + pad_y
    corners = [_merc(minlon, minlat), _merc(maxlon, minlat), _merc(minlon, maxlat), _merc(maxlon, maxlat)]
    minx, maxx = min(c[0] for c in corners), max(c[0] for c in corners)
    miny, maxy = min(c[1] for c in corners), max(c[1] for c in corners)
    W = width
    head, hh = figure_heading(t, title, subtitle, x=36)
    ox, oy, pw, ph = 48, hh, W - 84, 420
    H = oy + ph + 56
    sx, sy = (maxx - minx) or 1, (maxy - miny) or 1
    aspect, panel = sx / sy, pw / ph
    if aspect > panel:
        used_w, used_h = pw, pw / aspect
    else:
        used_h, used_w = ph, ph * aspect
    x0 = ox + (pw - used_w) / 2
    y0 = oy + (ph - used_h) / 2

    def proj(lon, lat):
        mx, my = _merc(lon, lat)
        return x0 + (mx - minx) / sx * used_w, y0 + (maxy - my) / sy * used_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" role="img" viewBox="0 0 {W} {H}" width="{W}"><title>{esc(title or "map")}</title>',
        f'<desc>{esc(subtitle or title or "map")}</desc>',
        f'<rect width="{W}" height="{H}" fill="{t["card"]}"/>',
    ]
    parts.extend(head)
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
        parts.append(f'<polygon points="{" ".join(seq)}" fill="{land}" stroke="{coast}" stroke-width="0.6"/>')
    return {"parts": parts, "proj": proj, "W": W, "H": H, "t": t, "x0": x0, "y0": y0,
            "used_w": used_w, "used_h": used_h, "ox": ox, "oy": oy, "water": water,
            "minlon": minlon, "maxlon": maxlon, "minlat": minlat, "maxlat": maxlat, "sx": sx}


def _map_finish(ctx, note):
    import math
    t, parts = ctx["t"], ctx["parts"]
    parts.append("</g>")
    parts.extend(ctx.get("after") or [])
    x0, y0, used_w, used_h, sx = ctx["x0"], ctx["y0"], ctx["used_w"], ctx["used_h"], ctx["sx"]
    midlat = (ctx["minlat"] + ctx["maxlat"]) / 2
    m_per_px = 6378137 * math.cos(math.radians(midlat)) / (used_w / sx) if used_w else 1
    target = used_w * 0.22 * m_per_px
    nice_m = 1
    for cand in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000):
        if cand * 1000 <= target:
            nice_m = cand
    bar_px = (nice_m * 1000) / m_per_px if m_per_px else 40
    bx, by = x0 + 12, y0 + used_h - 18
    parts.append(f'<rect x="{bx - 4:.1f}" y="{by - 18:.1f}" width="{bar_px + 12:.1f}" height="26" fill="{ctx["water"]}" fill-opacity="0.92"/>')
    parts.append(f'<line x1="{bx:.1f}" y1="{by:.1f}" x2="{bx + bar_px:.1f}" y2="{by:.1f}" stroke="{t["ink"]}" stroke-width="2"/>')
    unit = f"{nice_m} km" if nice_m < 1000 else f"{nice_m / 1000:g}k km"
    parts.append(f'<text x="{bx:.1f}" y="{by - 8:.1f}" font-size="10" font-family="{MONO}" fill="{t["ink"]}">{esc(unit)}</text>')
    nx, ny = x0 + used_w - 18, y0 + 22
    parts.append(f'<line x1="{nx:.1f}" y1="{ny + 16:.1f}" x2="{nx:.1f}" y2="{ny - 10:.1f}" stroke="{t["ink"]}" stroke-width="1.2"/>')
    parts.append(f'<polygon points="{nx:.1f},{ny - 16:.1f} {nx - 4:.1f},{ny - 6:.1f} {nx + 4:.1f},{ny - 6:.1f}" fill="{t["ink"]}"/>')
    parts.append(f'<text x="{nx + 8:.1f}" y="{ny - 8:.1f}" font-size="10" font-family="{MONO}" fill="{t["ink"]}">N</text>')
    parts.append(f'<text x="36" y="{ctx["H"] - 14}" font-size="10.5" font-family="{MONO}" fill="{t["soft"]}">{esc(note)} · Web Mercator</text>')
    parts.append("</svg>")
    return "\n".join(parts), ctx["W"], ctx["H"]

# --- chart renderers ---

_ROLE_ALIAS = {
    "x": ("x", "time", "ts", "date", "day", "at"),
    "y": ("y",),
    "val": ("val", "value", "v", "n", "count"),
    "size": ("size", "z", "r"),
    "cat": ("cat", "category", "name", "label"),
    "group": ("group", "series", "g"),
    "a": ("a", "left", "start", "before", "lo"),
    "b": ("b", "right", "end", "after", "hi"),
    "lo": ("lo", "low", "min", "lower"),
    "hi": ("hi", "high", "max", "upper"),
    "open": ("open", "o"),
    "high": ("high", "h"),
    "low": ("low", "l"),
    "close": ("close", "c"),
    "src": ("src", "from", "source"),
    "dst": ("dst", "to", "target"),
    "lat": ("lat", "latitude"),
    "lon": ("lon", "lng", "long", "longitude"),
    "lat2": ("lat2", "latitude2", "dst_lat"),
    "lon2": ("lon2", "lng2", "longitude2", "dst_lon"),
    "rank": ("rank", "r"),
    "name": ("name", "id", "node"),
    "parent": ("parent", "pid"),
    "axis": ("axis", "dim", "criteria"),
    "series": ("series", "group", "g"),
    "row": ("row", "r"),
    "col": ("col", "column", "c"),
    "state": ("state", "status"),
    "est": ("est", "estimate", "effect", "val", "value"),
    "bar": ("bar", "bars"),
    "line": ("line", "lines"),
    "z": ("z", "val", "value"),
    "date": ("date", "day", "at"),
    "label": ("label", "name"),
}


def _hh(title, sub):
    y = 8
    if title:
        y += 18
    if sub:
        y += 18
    return (y + 16) if (title or sub) else 8


def _short(text, n=28):
    text = str(text)
    return text if len(text) <= n else text[:n - 1] + "…"


def _ordered(vals):
    out = []
    for v in vals:
        if v not in out:
            out.append(v)
    return out


def _col(rows, explicit, role):
    return _pick(rows, explicit, _ROLE_ALIAS[role])


def _need(rows, pairs):
    found = {}
    missing = []
    for role, explicit in pairs:
        col = _col(rows, explicit, role)
        found[role] = col
        if not col:
            missing.append(role)
    if missing:
        raise SystemExit("need a column for " + ", ".join(missing))
    return found


def _floats(rows, col):
    out = []
    for r in rows:
        try:
            out.append((r, _f(r, col)))
        except (TypeError, ValueError, KeyError):
            continue
    if not out:
        raise SystemExit(f"column '{col}' has no numbers")
    return out


def _foot(opt, n, extra=""):
    bit = opt.get("source") or f"n={n}"
    return (bit + (" · " + extra if extra else "")).strip()


def _begin(opt, ph, ox=78, right=44, W=760, bottom=52):
    title, sub = opt["title"], opt["sub"]
    hh = _hh(title, sub)
    oy = hh + 10
    pw = W - ox - right
    H = int(oy + ph + bottom)
    parts, _hh_real = _fig_open(opt["t"], title, sub, W, H)
    return parts, opt["t"], W, H, ox, oy, pw, ph


def _done(parts, opt, W, H, n, extra=""):
    return _fig_close(parts, opt["t"], W, H, _foot(opt, n, extra)) + (n,)


def _domain(vals, floor0=True):
    lo, hi = min(vals), max(vals)
    if floor0 and lo >= 0:
        lo = 0.0
    if lo == hi:
        hi = lo + 1.0
    return lo, hi


def _dot(parts, t, x, y, r, col, on, hit):
    if hit:
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r + 2.5:.1f}" fill="{t["accent"]}" stroke="{t["card"]}" stroke-width="1.2"/>')
        return
    if not on:
        return
    parts.append(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{col}" stroke="{t["card"]}" stroke-width="1"/>')


def _legend(parts, t, items, x, y, limit=680):
    cx = x
    for col, lab in items:
        lab = _short(lab, 16)
        parts.append(f'<rect x="{cx:.1f}" y="{y - 8:.1f}" width="9" height="9" fill="{col}"/>')
        parts.append(
            f'<text x="{cx + 13:.1f}" y="{y:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}">{esc(lab)}</text>')
        cx += 13 + len(str(lab)) * 6.2 + 16
        if cx > limit:
            break


def _ramp(parts, t, x, y, w, lo, hi):
    steps = 10
    for i in range(steps):
        col = _heat_color(t, i / (steps - 1))
        parts.append(
            f'<rect x="{x + i * w / steps:.1f}" y="{y:.1f}" width="{w / steps + 0.5:.1f}" height="8" fill="{col}"/>')
    parts.append(
        f'<text x="{x:.1f}" y="{y + 20:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}">{esc(lo)}</text>')
    parts.append(
        f'<text x="{x + w:.1f}" y="{y + 20:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">{esc(hi)}</text>')


def _cat_labels(parts, t, labels, coords, y, rotate):
    for x, lab in zip(coords, labels):
        if rotate:
            parts.append(
                f'<text x="{x:.1f}" y="{y:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="end" transform="rotate(-32 {x:.1f} {y:.1f})">{esc(_short(lab, 18))}</text>')
        else:
            parts.append(
                f'<text x="{x:.1f}" y="{y:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(lab, 16))}</text>')


def _focals(nodes):
    out = []
    for n in nodes:
        if n.get("focal") and len(out) < 2:
            out.append(n.get("id"))
    return set(out)


def _with_ids(nodes):
    for i, n in enumerate(nodes):
        if not n.get("id"):
            n["id"] = str(n.get("name") or f"n{i}")
        if not n.get("name"):
            n["name"] = n["id"]
    return nodes


def _linked(opt, nodes, edges, cap_n, cap_e, gap_y=128):
    nodes = _with_ids(nodes)
    unbounded = _open_budget(opt.get("spec"), opt["unbounded"])
    _cap(opt.get("spec"), len(nodes), cap_n, "nodes", unbounded)
    _cap(opt.get("spec"), len(edges), cap_e, "edges", unbounded)
    rank = _layers_of(nodes, edges) if nodes else {}
    from collections import defaultdict
    rows = defaultdict(list)
    for n in nodes:
        rows[rank.get(n["id"], 0)].append(n)
    depth = max(rank.values()) if rank else 0
    widest = max((len(v) for v in rows.values()), default=1)
    W = max(760, 220 * (widest + 1))
    top = _hh(opt["title"], opt["sub"]) + 52
    H = int(top + max(depth, 0) * gap_y + 96)
    parts, _ = _fig_open(opt["t"], opt["title"], opt["sub"], W, H)
    parts.append(markers(opt["t"]))
    pos = _place_layers(nodes, rank, W, top, gap_y) if nodes else {}
    return parts, pos, W, H


def _paint_boxes(parts, t, pos, focals, w=160, h=56):
    for nid, (x, y, n) in pos.items():
        focal = nid in focals
        fill = t["accent_tint"] if focal else t["card"]
        stroke = t["accent"] if focal else t["ink"]
        sw = "1.5" if focal else "1.1"
        parts.append(
            f'<rect x="{x - w / 2:.1f}" y="{y - h / 2:.1f}" width="{w}" height="{h}" rx="2" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
        name = _short(n.get("name") or nid, 22)
        sub = n.get("sub") or ""
        parts.append(
            f'<text x="{x:.1f}" y="{y + (-2 if sub else 4):.1f}" font-size="13" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(name)}</text>')
        if sub:
            parts.append(
                f'<text x="{x:.1f}" y="{y + 16:.1f}" font-size="11" font-family="{FONT}" fill="{t["muted"]}" text-anchor="middle">{esc(_short(sub, 26))}</text>')


def _open_budget(spec, unbounded):
    return bool(unbounded) or (isinstance(spec, dict) and spec.get("budget") is False)


def _quartiles(vals):
    s = sorted(vals)
    n = len(s)

    def q(p):
        if n == 1:
            return s[0]
        i = p * (n - 1)
        lo = int(i)
        hi = min(lo + 1, n - 1)
        f = i - lo
        return s[lo] * (1 - f) + s[hi] * f

    return q(0.25), q(0.5), q(0.75)


def _parse_date(text):
    import datetime
    s = str(text).strip()
    for fmt, n in (("%Y-%m-%d", 10), ("%Y/%m/%d", 10), ("%Y-%m", 7), ("%Y/%m", 7), ("%Y", 4)):
        try:
            return datetime.datetime.strptime(s[:n], fmt)
        except ValueError:
            continue
    return None


def _when(text):
    import datetime
    try:
        return float(text), False
    except (TypeError, ValueError):
        d = _parse_date(text)
        if d is None:
            raise SystemExit(f"cannot read a date or number from '{text}'")
        return d.toordinal(), True


def _tree_from(nodes):
    rows = []
    by_id = {}
    for n in nodes:
        i = str(n.get("id") or n.get("name") or "")
        by_id[i] = str(n.get("name") or i)
    for n in nodes:
        i = str(n.get("id") or n.get("name") or "")
        parent = str(n.get("parent") or "")
        rows.append({
            "name": by_id.get(i, i),
            "parent": by_id.get(parent, parent),
            "val": n.get("val", n.get("value", 0)),
            "sub": n.get("sub") or "",
            "label": n.get("label") or n.get("edge") or "",
        })
    return _tree_index(rows)


def _leaf_pos(roots):
    pos = {}
    cursor = [0]

    def walk(node, depth):
        if not node["children"]:
            pos[id(node)] = [float(cursor[0]), depth]
            cursor[0] += 1
            return
        for child in node["children"]:
            walk(child, depth + 1)
        xs = [pos[id(c)][0] for c in node["children"]]
        pos[id(node)] = [sum(xs) / len(xs), depth]
    for root in roots:
        walk(root, 0)
    return pos, max(cursor[0], 1)


def _groups(rows, col):
    from collections import defaultdict
    g = defaultdict(list)
    if not col:
        g[""] = list(rows)
        return g
    for r in rows:
        g[str(r.get(col) or "")].append(r)
    return g


def _c_bubble(spec, rows, opt):
    c = _need(rows, [("x", opt["x"]), ("y", opt["y"]), ("size", opt["size"])])
    gc = _col(rows, opt["group"], "group")
    pts = []
    for r in rows:
        try:
            pts.append((r, _f(r, c["x"]), _f(r, c["y"]), _f(r, c["size"])))
        except (TypeError, ValueError):
            continue
    if not pts:
        raise SystemExit("bubble needs numeric x, y, and size")
    _cap(None, len(pts), 400, "points", opt["unbounded"])
    names = _ordered(str(r.get(gc) or "") for r, *_ in pts) if gc else [""]
    _cap(None, len(names), 8, "groups", opt["unbounded"])
    pal = series_palette(opt["t"])
    color = {name: (opt["t"]["link"] if len(names) == 1 else pal[i % len(pal)]) for i, name in enumerate(names)}
    xs = [p[1] for p in pts]
    ys = [p[2] for p in pts]
    ss = [max(0.0, p[3]) for p in pts]
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 320, bottom=78 if gc else 56)
    xt, yt = nice_ticks(*_domain(xs, floor0=min(xs) >= 0)), nice_ticks(*_domain(ys, floor0=min(ys) >= 0))
    X, Y = _axes(parts, t, ox, oy, pw, ph, xt, yt, opt["grid"])
    smax = max(ss) or 1
    for r, x, y, s in pts:
        name = str(r.get(gc) or "") if gc else ""
        hit = _hit(opt["highlights"], name, r.get(c["x"]))
        rad = 5 + 16 * (max(s, 0) / smax) ** 0.5
        _dot(parts, t, X(x), Y(y), rad, color[name], opt["markers"], hit)
    if gc and len(names) > 1:
        _legend(parts, t, [(color[n], n or "series") for n in names], ox, H - 36)
    return _done(parts, opt, W, H, len(pts))


def _c_beeswarm(spec, rows, opt):
    import math
    c = _need(rows, [("cat", opt["x"] or opt["label"]), ("val", opt["val"] or opt["y"])])
    packed = []
    for r, v in _floats(rows, c["val"]):
        packed.append((str(r.get(c["cat"]) or ""), v))
    _cap(None, len(packed), 300, "dots", opt["unbounded"])
    cats = _ordered(p[0] for p in packed)
    vals = [p[1] for p in packed]
    rotate = len(cats) > 6
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 320, bottom=78 if rotate else 56)
    yt = nice_ticks(*_domain(vals))
    span = (yt[-1] - yt[0]) or 1
    slot = pw / max(len(cats), 1)

    def Y(v):
        return oy + ph - (v - yt[0]) / span * ph

    parts.append(f'<line x1="{ox}" y1="{oy + ph}" x2="{ox + pw}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    parts.append(f'<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    for v in yt:
        y = Y(v)
        if opt["grid"]:
            parts.append(f'<line x1="{ox}" y1="{y:.1f}" x2="{ox + pw}" y2="{y:.1f}" stroke="{t["rule"]}"/>')
        parts.append(
            f'<text x="{ox - 8}" y="{y + 3:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">{fmt_tick(v)}</text>')
    centers = []
    for i, cat in enumerate(cats):
        cx = ox + (i + 0.5) * slot
        centers.append(cx)
        here = [(v, Y(v)) for name, v in packed if name == cat]
        placed = []
        for v, y in here:
            x, sign, step = cx, 1, 0
            for _try in range(30):
                if not any(math.hypot(x - px, y - py) < 11 for px, py in placed):
                    break
                step += 1
                x = cx + (step // 2 + 1) * 6 * (1 if step % 2 else -1)
            x = min(ox + pw - 8, max(ox + 8, x))
            placed.append((x, y))
            _dot(parts, t, x, y, 4.5, t["link"], opt["markers"], _hit(opt["highlights"], cat))
    _cat_labels(parts, t, cats, centers, oy + ph + 16, rotate)
    return _done(parts, opt, W, H, len(packed))


def _c_step(spec, rows, opt):
    c = _need(rows, [("x", opt["x"]), ("y", opt["y"])])
    gc = _col(rows, opt["group"], "group")
    series = {}
    for r in rows:
        try:
            series.setdefault(str(r.get(gc) or "") if gc else "", []).append((_f(r, c["x"]), _f(r, c["y"])))
        except (TypeError, ValueError):
            continue
    if not series:
        raise SystemExit("step needs numeric x and y")
    names = _ordered(series)
    _cap(None, len(names), 6, "series", opt["unbounded"])
    pal = series_palette(opt["t"])
    xs = [p[0] for pts in series.values() for p in pts]
    ys = [p[1] for pts in series.values() for p in pts]
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 300, bottom=72 if len(names) > 1 else 52)
    X, Y = _axes(parts, t, ox, oy, pw, ph, nice_ticks(*_domain(xs)), nice_ticks(*_domain(ys)), opt["grid"])
    for i, name in enumerate(names):
        pts = sorted(series[name])
        col = t["link"] if len(names) == 1 else pal[i % len(pal)]
        d = [f"M {X(pts[0][0]):.1f} {Y(pts[0][1]):.1f}"]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            d.append(f"H {X(x1):.1f} V {Y(y1):.1f}")
        parts.append(f'<path d="{" ".join(d)}" fill="none" stroke="{col}" stroke-width="1.8"/>')
        if opt["markers"] or _hit(opt["highlights"], name):
            for x, y in pts:
                _dot(parts, t, X(x), Y(y), 3.2, col, opt["markers"], _hit(opt["highlights"], name, x))
    if len(names) > 1:
        _legend(parts, t, [(pal[i % len(pal)], n or "series") for i, n in enumerate(names)], ox, H - 34)
    return _done(parts, opt, W, H, sum(len(v) for v in series.values()))


def _c_slope(spec, rows, opt):
    c = _need(rows, [("cat", opt["label"] or opt["x"]), ("a", opt["a"]), ("b", opt["b"])])
    items = []
    for r in rows:
        try:
            items.append((str(r.get(c["cat"]) or ""), _f(r, c["a"]), _f(r, c["b"])))
        except (TypeError, ValueError):
            continue
    if not items:
        raise SystemExit("slope needs cat, a, and b")
    _cap(None, len(items), 16, "lines", opt["unbounded"])
    vals = [v for _, a, b in items for v in (a, b)]
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, max(280, 36 + len(items) * 8), ox=120, right=130)
    lo, hi = _domain(vals, floor0=min(vals) >= 0)
    yt = nice_ticks(lo, hi)
    span = (yt[-1] - yt[0]) or 1

    def Y(v):
        return oy + ph - (v - yt[0]) / span * ph

    x1, x2 = ox + 10, ox + pw - 10
    for lab, anchor, x in (("A", "end", x1 - 8), ("B", "start", x2 + 8)):
        parts.append(
            f'<text x="{x}" y="{oy - 6}" font-size="11" font-family="{FONT}" fill="{t["muted"]}" text-anchor="{anchor}">{lab}</text>')
    for v in yt:
        y = Y(v)
        if opt["grid"]:
            parts.append(f'<line x1="{x1}" y1="{y:.1f}" x2="{x2}" y2="{y:.1f}" stroke="{t["rule"]}"/>')
    pal = series_palette(t)
    for i, (name, a, b) in enumerate(items):
        col = t["accent"] if _hit(opt["highlights"], name) else (t["link"] if len(items) == 1 else pal[i % len(pal)])
        parts.append(
            f'<line x1="{x1}" y1="{Y(a):.1f}" x2="{x2}" y2="{Y(b):.1f}" stroke="{col}" stroke-width="1.6"/>')
        if opt["markers"] or _hit(opt["highlights"], name):
            _dot(parts, t, x1, Y(a), 3.4, col, True, False)
            _dot(parts, t, x2, Y(b), 3.4, col, True, False)
        parts.append(
            f'<text x="{x1 - 10}" y="{Y(a) + 3:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="end">{esc(_short(name, 16))}</text>')
        if opt["markers"]:
            parts.append(
                f'<text x="{x2 + 10}" y="{Y(b) + 3:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}">{fmt_tick(b)}</text>')
    return _done(parts, opt, W, H, len(items))


def _c_bump(spec, rows, opt):
    c = _need(rows, [("x", opt["x"]), ("name", opt["label"]), ("rank", opt["y"] or opt["val"])])
    series = {}
    order = []
    for r in rows:
        try:
            name = str(r.get(c["name"]) or "")
            series.setdefault(name, []).append((str(r.get(c["x"]) or ""), _f(r, c["rank"])))
            if str(r.get(c["x"]) or "") not in order:
                order.append(str(r.get(c["x"]) or ""))
        except (TypeError, ValueError):
            continue
    if not series:
        raise SystemExit("bump needs x, name, and rank")
    _cap(None, len(series), 8, "names", opt["unbounded"])
    ranks = [p[1] for pts in series.values() for p in pts]
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 300, bottom=72)
    top, bot = min(ranks), max(ranks)
    span = (bot - top) or 1

    def Y(v):
        return oy + (v - top) / span * ph

    xs = [ox + (i + 0.5) * pw / max(len(order), 1) for i in range(len(order))]
    pal = series_palette(t)
    names = list(series)
    for i, name in enumerate(names):
        col = t["accent"] if _hit(opt["highlights"], name) else pal[i % len(pal)]
        pts = sorted(series[name], key=lambda p: order.index(p[0]) if p[0] in order else 0)
        d = " ".join(f'{"M" if j == 0 else "L"} {xs[order.index(x)]:.1f} {Y(rk):.1f}' for j, (x, rk) in enumerate(pts) if x in order)
        if d:
            parts.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="1.7"/>')
        if opt["markers"] or _hit(opt["highlights"], name):
            for x, rk in pts:
                if x in order:
                    _dot(parts, t, xs[order.index(x)], Y(rk), 3.5, col, True, _hit(opt["highlights"], name))
    _cat_labels(parts, t, order, xs, oy + ph + 18, len(order) > 6)
    _legend(parts, t, [(pal[i % len(pal)], n) for i, n in enumerate(names)], ox, H - 34)
    return _done(parts, opt, W, H, len(series))


def _c_ridgeline(spec, rows, opt):
    import math
    c = _need(rows, [("group", opt["group"]), ("val", opt["val"] or opt["y"])])
    groups = _groups(rows, c["group"])
    names = _ordered(groups)
    _cap(None, len(names), 8, "groups", opt["unbounded"])
    vals = []
    for name in names:
        vals.extend(v for _, v in _floats(groups[name], c["val"]))
    lo, hi = min(vals), max(vals)
    if lo == hi:
        hi = lo + 1
    k = max(5, min(16, int(math.ceil(math.log2(max(len(vals), 2)) + 1))))
    edges = [lo + (hi - lo) * i / k for i in range(k + 1)]
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, max(280, 36 * len(names) + 40))
    band = ph / max(len(names), 1)
    pal = series_palette(t)
    parts.append(f'<line x1="{ox}" y1="{oy + ph}" x2="{ox + pw}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    for i, name in enumerate(names):
        counts = [0] * k
        for _, v in _floats(groups[name], c["val"]):
            idx = min(k - 1, int((v - lo) / (hi - lo) * k))
            counts[idx] += 1
        peak = max(counts) or 1
        base = oy + (i + 1) * band - 8
        col = t["accent"] if _hit(opt["highlights"], name) else pal[i % len(pal)]
        d = [f"M {ox:.1f} {base:.1f}"]
        for j, count in enumerate(counts):
            x0 = ox + j * pw / k
            x1 = ox + (j + 1) * pw / k
            y = base - (count / peak) * (band - 16)
            d.append(f"L {x0:.1f} {y:.1f} L {x1:.1f} {y:.1f}")
        d.append(f"L {ox + pw:.1f} {base:.1f} Z")
        parts.append(f'<path d="{" ".join(d)}" fill="{col}" fill-opacity="0.35" stroke="{col}" stroke-width="1.2"/>')
        parts.append(
            f'<text x="{ox - 8}" y="{base:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="end">{esc(_short(name, 14))}</text>')
    parts.append(
        f'<text x="{ox}" y="{oy + ph + 16}" font-size="10" font-family="{FONT}" fill="{t["muted"]}">{fmt_tick(lo)}</text>')
    parts.append(
        f'<text x="{ox + pw}" y="{oy + ph + 16}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">{fmt_tick(hi)}</text>')
    return _done(parts, opt, W, H, len(vals), "value along the ridge")


def _c_stack(spec, rows, opt):
    c = _need(rows, [("cat", opt["x"] or opt["label"]), ("group", opt["group"]), ("val", opt["val"] or opt["y"])])
    cats, groups = [], []
    cell = {}
    for r in rows:
        try:
            cat, grp, val = str(r.get(c["cat"]) or ""), str(r.get(c["group"]) or ""), _f(r, c["val"])
        except (TypeError, ValueError):
            continue
        if cat not in cats:
            cats.append(cat)
        if grp not in groups:
            groups.append(grp)
        cell[(cat, grp)] = cell.get((cat, grp), 0) + val
    if not cats:
        raise SystemExit("stack needs cat, group, and val")
    _cap(None, len(cats), 12, "categories", opt["unbounded"])
    _cap(None, len(groups), 8, "groups", opt["unbounded"])
    totals = []
    for cat in cats:
        pos = sum(v for g in groups for v in [cell.get((cat, g), 0)] if v > 0)
        neg = sum(v for g in groups for v in [cell.get((cat, g), 0)] if v < 0)
        totals.extend((pos, neg))
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 300, bottom=78)
    yt = axis_ticks(*_domain(totals, floor0=min(totals) >= 0))
    span = (yt[-1] - yt[0]) or 1

    def Y(v):
        return oy + ph - (v - yt[0]) / span * ph

    slot = pw / len(cats)
    bw = min(46, slot * 0.62)
    pal = series_palette(t)
    parts.append(f'<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    parts.append(f'<line x1="{ox}" y1="{Y(0):.1f}" x2="{ox + pw}" y2="{Y(0):.1f}" stroke="{t["ink"]}" stroke-width="1"/>')
    for v in yt:
        y = Y(v)
        if opt["grid"]:
            parts.append(f'<line x1="{ox}" y1="{y:.1f}" x2="{ox + pw}" y2="{y:.1f}" stroke="{t["rule"]}"/>')
        parts.append(
            f'<text x="{ox - 8}" y="{y + 3:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">{fmt_tick(v)}</text>')
    centers = []
    for i, cat in enumerate(cats):
        cx = ox + (i + 0.5) * slot
        centers.append(cx)
        pos = neg = 0.0
        hit = _hit(opt["highlights"], cat)
        for j, grp in enumerate(groups):
            val = cell.get((cat, grp), 0)
            if val == 0:
                continue
            y0 = pos if val > 0 else neg
            y1 = y0 + val
            if val > 0:
                pos = y1
            else:
                neg = y1
            top, bot = Y(max(y0, y1)), Y(min(y0, y1))
            col = t["accent"] if hit else pal[j % len(pal)]
            parts.append(
                f'<rect x="{cx - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(1, bot - top):.1f}" fill="{col}"/>')
    _cat_labels(parts, t, cats, centers, oy + ph + 16, len(cats) > 6)
    _legend(parts, t, [(pal[i % len(pal)], g) for i, g in enumerate(groups)], ox, H - 34)
    return _done(parts, opt, W, H, len(cats))


def _c_dumbbell(spec, rows, opt):
    c = _need(rows, [("cat", opt["label"] or opt["x"]), ("a", opt["a"] or opt["lo"]), ("b", opt["b"] or opt["hi"])])
    items = []
    for r in rows:
        try:
            items.append((str(r.get(c["cat"]) or ""), _f(r, c["a"]), _f(r, c["b"])))
        except (TypeError, ValueError):
            continue
    if not items:
        raise SystemExit("dumbbell needs cat, a, and b")
    _cap(None, len(items), 16, "rows", opt["unbounded"])
    vals = [v for _, a, b in items for v in (a, b)]
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, max(240, len(items) * 32), ox=130, right=36)
    xt = nice_ticks(*_domain(vals))
    span = (xt[-1] - xt[0]) or 1

    def X(v):
        return ox + (v - xt[0]) / span * pw

    parts.append(f'<line x1="{ox}" y1="{oy + ph}" x2="{ox + pw}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    for v in xt:
        x = X(v)
        if opt["grid"]:
            parts.append(f'<line x1="{x:.1f}" y1="{oy}" x2="{x:.1f}" y2="{oy + ph}" stroke="{t["rule"]}"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{oy + ph + 16}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="middle">{fmt_tick(v)}</text>')
    for i, (name, a, b) in enumerate(items):
        y = oy + (i + 0.5) * ph / len(items)
        hit = _hit(opt["highlights"], name)
        col = t["accent"] if hit else t["link"]
        parts.append(f'<line x1="{X(a):.1f}" y1="{y:.1f}" x2="{X(b):.1f}" y2="{y:.1f}" stroke="{col}" stroke-width="1.6"/>')
        _dot(parts, t, X(a), y, 4.5, t["muted"], opt["markers"] or hit, False)
        _dot(parts, t, X(b), y, 4.5, col, opt["markers"] or hit, hit)
        parts.append(
            f'<text x="{ox - 8}" y="{y + 3:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="end">{esc(_short(name, 16))}</text>')
    return _done(parts, opt, W, H, len(items))


def _c_waterfall(spec, rows, opt):
    c = _need(rows, [("cat", opt["x"] or opt["label"]), ("val", opt["val"] or opt["y"])])
    items = []
    for r in rows:
        try:
            items.append((str(r.get(c["cat"]) or ""), _f(r, c["val"])))
        except (TypeError, ValueError):
            continue
    if not items:
        raise SystemExit("waterfall needs cat and val")
    _cap(None, len(items), 16, "steps", opt["unbounded"])
    running = 0.0
    spans = []
    for name, val in items:
        if name.strip().lower() in ("total", "net", "end"):
            spans.append((name, 0.0, val, "total"))
            running = val
        else:
            spans.append((name, running, running + val, "up" if val >= 0 else "down"))
            running += val
    bounds = [v for _, a, b, _ in spans for v in (a, b)]
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 300, bottom=78)
    yt = axis_ticks(*_domain(bounds))
    span = (yt[-1] - yt[0]) or 1

    def Y(v):
        return oy + ph - (v - yt[0]) / span * ph

    parts.append(f'<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    zero = Y(0)
    parts.append(f'<line x1="{ox}" y1="{zero:.1f}" x2="{ox + pw}" y2="{zero:.1f}" stroke="{t["ink"]}" stroke-width="1"/>')
    for v in yt:
        y = Y(v)
        if opt["grid"]:
            parts.append(f'<line x1="{ox}" y1="{y:.1f}" x2="{ox + pw}" y2="{y:.1f}" stroke="{t["rule"]}"/>')
        parts.append(
            f'<text x="{ox - 8}" y="{y + 3:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">{fmt_tick(v)}</text>')
    slot = pw / len(spans)
    bw = min(42, slot * 0.62)
    prev = None
    centers = []
    for i, (name, a, b, kind) in enumerate(spans):
        cx = ox + (i + 0.5) * slot
        centers.append(cx)
        top, bot = Y(max(a, b)), Y(min(a, b))
        col = t["ink"] if kind == "total" else (t["link"] if kind == "up" else t["accent"])
        if _hit(opt["highlights"], name):
            col = t["accent"]
        parts.append(
            f'<rect x="{cx - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(1, bot - top):.1f}" fill="{col}"/>')
        if prev is not None and kind != "total":
            parts.append(
                f'<line x1="{prev:.1f}" y1="{Y(a):.1f}" x2="{cx - bw / 2:.1f}" y2="{Y(a):.1f}" stroke="{t["soft"]}" stroke-dasharray="3 3"/>')
        prev = cx + bw / 2
        if opt["markers"]:
            parts.append(
                f'<text x="{cx:.1f}" y="{top - 4:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="middle">{fmt_tick(b - a if kind != "total" else b)}</text>')
    _cat_labels(parts, t, [s[0] for s in spans], centers, oy + ph + 16, len(spans) > 6)
    return _done(parts, opt, W, H, len(spans))


def _hist_edges(vals):
    import math
    lo, hi = min(vals), max(vals)
    if lo == hi:
        hi = lo + 1
    k = int(math.ceil(math.log2(len(vals)) + 1))
    k = max(5, min(20, k))
    step = (hi - lo) / k
    return [lo + i * step for i in range(k + 1)], k


def _c_histogram(spec, rows, opt):
    c = _need(rows, [("val", opt["val"] or opt["y"] or opt["x"])])
    vals = [v for _, v in _floats(rows, c["val"])]
    _cap(None, len(vals), 400, "values", opt["unbounded"])
    edges, k = _hist_edges(vals)
    counts = [0] * k
    span = edges[-1] - edges[0]
    for v in vals:
        counts[min(k - 1, int((v - edges[0]) / span * k))] += 1
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 300)
    yt = axis_ticks(0, max(counts))
    yspan = (yt[-1] - yt[0]) or 1

    def Y(v):
        return oy + ph - (v - yt[0]) / yspan * ph

    parts.append(f'<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    parts.append(f'<line x1="{ox}" y1="{oy + ph}" x2="{ox + pw}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    for v in yt:
        y = Y(v)
        if opt["grid"]:
            parts.append(f'<line x1="{ox}" y1="{y:.1f}" x2="{ox + pw}" y2="{y:.1f}" stroke="{t["rule"]}"/>')
        parts.append(
            f'<text x="{ox - 8}" y="{y + 3:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">{fmt_tick(v)}</text>')
    bw = pw / k
    for i, count in enumerate(counts):
        top = Y(count)
        parts.append(
            f'<rect x="{ox + i * bw + 1:.1f}" y="{top:.1f}" width="{bw - 2:.1f}" height="{max(0, oy + ph - top):.1f}" fill="{t["link"]}"/>')
    for i in (0, k // 2, k):
        x = ox + i * bw
        parts.append(
            f'<text x="{x:.1f}" y="{oy + ph + 16}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="middle">{fmt_tick(edges[i])}</text>')
    return _done(parts, opt, W, H, len(vals), f"{k} bins")


def _box_stats(vals):
    q1, med, q3 = _quartiles(vals)
    iqr = q3 - q1
    lo_f, hi_f = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    inside = [v for v in vals if lo_f <= v <= hi_f]
    whisk_lo = min(inside) if inside else q1
    whisk_hi = max(inside) if inside else q3
    outliers = [v for v in vals if v < lo_f or v > hi_f]
    return q1, med, q3, whisk_lo, whisk_hi, outliers


def _c_box(spec, rows, opt):
    c = _need(rows, [("group", opt["group"] or opt["x"]), ("val", opt["val"] or opt["y"])])
    groups = _groups(rows, c["group"])
    names = _ordered(groups)
    _cap(None, len(names), 8, "groups", opt["unbounded"])
    stats = []
    allv = []
    for name in names:
        vals = [v for _, v in _floats(groups[name], c["val"])]
        allv.extend(vals)
        stats.append((name, vals, _box_stats(vals)))
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 300, bottom=70)
    yt = nice_ticks(*_domain(allv))
    span = (yt[-1] - yt[0]) or 1

    def Y(v):
        return oy + ph - (v - yt[0]) / span * ph

    parts.append(f'<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    parts.append(f'<line x1="{ox}" y1="{oy + ph}" x2="{ox + pw}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    for v in yt:
        y = Y(v)
        if opt["grid"]:
            parts.append(f'<line x1="{ox}" y1="{y:.1f}" x2="{ox + pw}" y2="{y:.1f}" stroke="{t["rule"]}"/>')
        parts.append(
            f'<text x="{ox - 8}" y="{y + 3:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">{fmt_tick(v)}</text>')
    slot = pw / len(names)
    centers = []
    for i, (name, vals, (q1, med, q3, wlo, whi, outs)) in enumerate(stats):
        cx = ox + (i + 0.5) * slot
        centers.append(cx)
        bw = min(36, slot * 0.45)
        hit = _hit(opt["highlights"], name)
        col = t["accent"] if hit else t["link"]
        parts.append(f'<line x1="{cx:.1f}" y1="{Y(wlo):.1f}" x2="{cx:.1f}" y2="{Y(whi):.1f}" stroke="{col}" stroke-width="1.2"/>')
        parts.append(f'<line x1="{cx - 8:.1f}" y1="{Y(wlo):.1f}" x2="{cx + 8:.1f}" y2="{Y(wlo):.1f}" stroke="{col}"/>')
        parts.append(f'<line x1="{cx - 8:.1f}" y1="{Y(whi):.1f}" x2="{cx + 8:.1f}" y2="{Y(whi):.1f}" stroke="{col}"/>')
        top, bot = Y(q3), Y(q1)
        parts.append(
            f'<rect x="{cx - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(1, bot - top):.1f}" fill="{t["card"]}" stroke="{col}" stroke-width="1.4"/>')
        parts.append(f'<line x1="{cx - bw / 2:.1f}" y1="{Y(med):.1f}" x2="{cx + bw / 2:.1f}" y2="{Y(med):.1f}" stroke="{col}" stroke-width="1.6"/>')
        if opt["markers"]:
            for v in outs:
                _dot(parts, t, cx, Y(v), 2.8, col, True, False)
    _cat_labels(parts, t, names, centers, oy + ph + 16, len(names) > 6)
    return _done(parts, opt, W, H, sum(len(s[1]) for s in stats))


def _c_violin(spec, rows, opt):
    import math
    c = _need(rows, [("group", opt["group"] or opt["x"]), ("val", opt["val"] or opt["y"])])
    groups = _groups(rows, c["group"])
    names = _ordered(groups)
    _cap(None, len(names), 8, "groups", opt["unbounded"])
    series = []
    allv = []
    for name in names:
        vals = [v for _, v in _floats(groups[name], c["val"])]
        _cap(None, len(vals), 400, "values", opt["unbounded"])
        allv.extend(vals)
        series.append((name, vals, _box_stats(vals)))
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 300, bottom=70)
    yt = nice_ticks(*_domain(allv))
    span = (yt[-1] - yt[0]) or 1

    def Y(v):
        return oy + ph - (v - yt[0]) / span * ph

    parts.append(f'<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    parts.append(f'<line x1="{ox}" y1="{oy + ph}" x2="{ox + pw}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    for v in yt:
        y = Y(v)
        if opt["grid"]:
            parts.append(f'<line x1="{ox}" y1="{y:.1f}" x2="{ox + pw}" y2="{y:.1f}" stroke="{t["rule"]}"/>')
        parts.append(
            f'<text x="{ox - 8}" y="{y + 3:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">{fmt_tick(v)}</text>')
    slot = pw / len(names)
    half = min(28, slot * 0.38)
    centers = []
    for i, (name, vals, (q1, med, q3, wlo, whi, _)) in enumerate(series):
        cx = ox + (i + 0.5) * slot
        centers.append(cx)
        n = len(vals)
        sd = (sum((v - (sum(vals) / n)) ** 2 for v in vals) / n) ** 0.5 or 1
        bw = 1.06 * sd * n ** (-0.2)
        grid = [min(vals) + (max(vals) - min(vals)) * j / 31 for j in range(32)]
        if grid[0] == grid[-1]:
            grid = [grid[0] - 1, grid[0] + 1]
        dens = []
        for x in grid:
            s = sum(math.exp(-0.5 * ((x - v) / bw) ** 2) for v in vals)
            dens.append(s)
        peak = max(dens) or 1
        col = t["accent"] if _hit(opt["highlights"], name) else t["link"]
        right = [f"{cx + half * d / peak:.1f},{Y(x):.1f}" for x, d in zip(grid, dens)]
        left = [f"{cx - half * d / peak:.1f},{Y(x):.1f}" for x, d in zip(reversed(grid), reversed(dens))]
        parts.append(f'<polygon points="{" ".join(right + left)}" fill="{col}" fill-opacity="0.22" stroke="{col}" stroke-width="1.2"/>')
        parts.append(f'<line x1="{cx:.1f}" y1="{Y(wlo):.1f}" x2="{cx:.1f}" y2="{Y(whi):.1f}" stroke="{t["ink"]}" stroke-width="1.2"/>')
        parts.append(
            f'<rect x="{cx - 5:.1f}" y="{Y(q3):.1f}" width="10" height="{max(1, Y(q1) - Y(q3)):.1f}" fill="{t["card"]}" stroke="{t["ink"]}"/>')
        parts.append(f'<line x1="{cx - 5:.1f}" y1="{Y(med):.1f}" x2="{cx + 5:.1f}" y2="{Y(med):.1f}" stroke="{t["ink"]}"/>')
    _cat_labels(parts, t, names, centers, oy + ph + 16, len(names) > 6)
    return _done(parts, opt, W, H, sum(len(s[1]) for s in series))


def _c_strip(spec, rows, opt):
    c = _need(rows, [("group", opt["group"] or opt["x"]), ("val", opt["val"] or opt["y"])])
    groups = _groups(rows, c["group"])
    names = _ordered(groups)
    _cap(None, len(names), 8, "groups", opt["unbounded"])
    allv = []
    series = []
    for name in names:
        vals = [v for _, v in _floats(groups[name], c["val"])]
        _cap(None, len(vals), 400, "dots", opt["unbounded"])
        allv.extend(vals)
        series.append((name, vals))
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 300, bottom=70)
    yt = nice_ticks(*_domain(allv))
    span = (yt[-1] - yt[0]) or 1

    def Y(v):
        return oy + ph - (v - yt[0]) / span * ph

    parts.append(f'<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    parts.append(f'<line x1="{ox}" y1="{oy + ph}" x2="{ox + pw}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    for v in yt:
        y = Y(v)
        if opt["grid"]:
            parts.append(f'<line x1="{ox}" y1="{y:.1f}" x2="{ox + pw}" y2="{y:.1f}" stroke="{t["rule"]}"/>')
        parts.append(
            f'<text x="{ox - 8}" y="{y + 3:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">{fmt_tick(v)}</text>')
    slot = pw / len(names)
    centers = []
    for i, (name, vals) in enumerate(series):
        cx = ox + (i + 0.5) * slot
        centers.append(cx)
        hit = _hit(opt["highlights"], name)
        for j, v in enumerate(vals):
            jitter = ((j * 17) % 11) - 5
            _dot(parts, t, cx + jitter, Y(v), 3.4, t["link"], opt["markers"], hit)
    _cat_labels(parts, t, names, centers, oy + ph + 16, len(names) > 6)
    return _done(parts, opt, W, H, sum(len(s[1]) for s in series))


def _shares(rows, cat, val):
    items = []
    for r in rows:
        try:
            items.append((str(r.get(cat) or ""), _f(r, val)))
        except (TypeError, ValueError):
            continue
    items = [(n, v) for n, v in items if v > 0]
    if not items:
        raise SystemExit("need a positive value")
    return items


def _c_pie(spec, rows, opt, hole=0):
    import math
    c = _need(rows, [("cat", opt["label"] or opt["x"]), ("val", opt["val"] or opt["y"])])
    items = _shares(rows, c["cat"], c["val"])
    _cap(None, len(items), 8, "slices", opt["unbounded"])
    total = sum(v for _, v in items) or 1
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 340, ox=40, right=40, bottom=36)
    cx, cy, r = W / 2 - 70, oy + ph / 2, min(pw, ph) * 0.38
    pal = series_palette(t)
    ang = -math.pi / 2
    for i, (name, val) in enumerate(items):
        span = val / total * math.tau
        col = t["accent"] if _hit(opt["highlights"], name) else pal[i % len(pal)]
        a1 = ang + span
        if span >= math.tau - 1e-3:
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{col}"/>')
        else:
            large = 1 if span > math.pi else 0
            x0, y0 = cx + r * math.cos(ang), cy + r * math.sin(ang)
            x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
            parts.append(
                f'<path d="M {cx:.1f} {cy:.1f} L {x0:.1f} {y0:.1f} A {r:.1f} {r:.1f} 0 {large} 1 {x1:.1f} {y1:.1f} Z" fill="{col}"/>')
        mid = ang + span / 2
        lx, ly = cx + (r + 18) * math.cos(mid), cy + (r + 18) * math.sin(mid)
        anchor = "start" if math.cos(mid) >= 0 else "end"
        parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="{anchor}">{esc(_short(name, 14))} {val / total * 100:.0f}%</text>')
        ang = a1
    if hole:
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.58:.1f}" fill="{t["paper"]}"/>')
    return _done(parts, opt, W, H, len(items))


def _c_donut(spec, rows, opt):
    return _c_pie(spec, rows, opt, hole=1)


def _c_waffle(spec, rows, opt):
    c = _need(rows, [("cat", opt["label"] or opt["x"]), ("val", opt["val"] or opt["y"])])
    items = _shares(rows, c["cat"], c["val"])
    _cap(None, len(items), 8, "shares", opt["unbounded"])
    total = sum(v for _, v in items) or 1
    cells = [max(0, int(round(v / total * 100))) for _, v in items]
    drift = 100 - sum(cells)
    cells[max(range(len(cells)), key=lambda i: items[i][1])] += drift
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 320, bottom=70)
    size, gap = 22, 4
    pal = series_palette(t)
    painted = []
    for i, ncell in enumerate(cells):
        painted.extend([i] * max(0, ncell))
    painted = painted[:100]
    x0 = ox + 20
    y0 = oy + 10
    for i, owner in enumerate(painted):
        col = pal[owner % len(pal)]
        if _hit(opt["highlights"], items[owner][0]):
            col = t["accent"]
        gx, gy = i % 10, i // 10
        parts.append(
            f'<rect x="{x0 + gx * (size + gap):.1f}" y="{y0 + gy * (size + gap):.1f}" width="{size}" height="{size}" rx="2" fill="{col}"/>')
    _legend(parts, t, [(pal[i % len(pal)], f"{name} {cells[i]}") for i, (name, _) in enumerate(items)], ox, H - 34)
    return _done(parts, opt, W, H, 100, "100 cells")


def _csv_tree(rows, opt):
    c = _need(rows, [("name", opt["label"]), ("val", opt["val"] or opt["y"])])
    parent = _col(rows, opt["parent"], "parent")
    nodes = []
    for r in rows:
        name = str(r.get(c["name"]) or "")
        if not name:
            continue
        try:
            val = float(r[c["val"]]) if r.get(c["val"]) not in ("", None) else 0
        except (TypeError, ValueError):
            val = 0
        nodes.append({"name": name, "parent": str(r.get(parent) or "") if parent else "", "val": val})
    roots = _tree_index(nodes)
    if not roots:
        raise SystemExit("tree needs a name column")
    return roots


def _c_treemap(spec, rows, opt):
    roots = _csv_tree(rows, opt) if spec is None else _tree_from(spec.get("nodes") or [])
    if not roots:
        raise SystemExit("treemap needs nodes")
    n = sum(1 for _ in _walk_tree(roots))
    _cap(spec, n, 40, "nodes", opt["unbounded"])
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 360, ox=36, right=36)
    pal = series_palette(t)
    rects = _partition([(node, node["val"]) for node in roots], ox, oy, pw, ph, True)
    for i, (node, x, y, w, h) in enumerate(rects):
        _paint_tree_rect(parts, t, node, x, y, w, h, pal[i % len(pal)], opt)
    return _done(parts, opt, W, H, n)


def _walk_tree(roots):
    stack = list(roots)
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node["children"])


def _paint_tree_rect(parts, t, node, x, y, w, h, col, opt):
    kids = [(c, c["val"]) for c in node["children"]]
    hit = _hit(opt["highlights"], node["name"])
    fill = t["accent"] if hit else col
    if kids and w > 28 and h > 28:
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0):.1f}" height="{max(h, 0):.1f}" fill="{t["paper"]}" stroke="{t["card"]}"/>')
        if h > 18:
            parts.append(
                f'<text x="{x + 6:.1f}" y="{y + 14:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}">{esc(_short(node["name"], 18))}</text>')
        inner = _partition(kids, x + 2, y + 18, max(0, w - 4), max(0, h - 20), False)
        for child, cx, cy, cw, ch in inner:
            _paint_tree_rect(parts, t, child, cx, cy, cw, ch, col, opt)
        return
    parts.append(
        f'<rect x="{x + 1:.1f}" y="{y + 1:.1f}" width="{max(w - 2, 0):.1f}" height="{max(h - 2, 0):.1f}" fill="{fill}" fill-opacity="0.82" stroke="{t["paper"]}"/>')
    if w > 46 and h > 22:
        parts.append(
            f'<text x="{x + 6:.1f}" y="{y + 16:.1f}" font-size="11" font-family="{FONT}" fill="{t["card"]}">{esc(_short(node["name"], int(w / 7)))}</text>')
        if opt["markers"] and h > 34:
            parts.append(
                f'<text x="{x + 6:.1f}" y="{y + 30:.1f}" font-size="10" font-family="{FONT}" fill="{t["card"]}">{fmt_tick(node["val"])}</text>')


def _c_icicle(spec, rows, opt):
    roots = _csv_tree(rows, opt) if spec is None else _tree_from(spec.get("nodes") or [])
    n = sum(1 for _ in _walk_tree(roots))
    _cap(spec, n, 40, "nodes", opt["unbounded"])
    depth = _depth(roots)
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, max(280, depth * 56), ox=28, right=28)
    band = ph / max(depth, 1)
    pal = series_palette(t)

    def walk(node, x, y, w, d, color):
        hit = _hit(opt["highlights"], node["name"])
        parts.append(
            f'<rect x="{x + 1:.1f}" y="{y + 1:.1f}" width="{max(w - 2, 0):.1f}" height="{max(band - 2, 0):.1f}" fill="{t["accent"] if hit else color}" fill-opacity="0.85" stroke="{t["paper"]}"/>')
        if w > 48:
            parts.append(
                f'<text x="{x + 6:.1f}" y="{y + band / 2 + 4:.1f}" font-size="11" font-family="{FONT}" fill="{t["card"]}">{esc(_short(node["name"], int(w / 7)))}</text>')
        kids = node["children"]
        if not kids:
            return
        total = sum(c["val"] for c in kids) or 1
        acc = x
        for i, child in enumerate(kids):
            cw = w * child["val"] / total
            walk(child, acc, y + band, cw, d + 1, pal[(d + 1 + i) % len(pal)])
            acc += cw

    total = sum(r["val"] for r in roots) or 1
    acc = ox
    for i, root in enumerate(roots):
        w = pw * root["val"] / total
        walk(root, acc, oy, w, 0, pal[i % len(pal)])
        acc += w
    return _done(parts, opt, W, H, n)


def _depth(roots):
    best = 1

    def walk(node, d):
        nonlocal best
        best = max(best, d)
        for child in node["children"]:
            walk(child, d + 1)
    for root in roots:
        walk(root, 1)
    return best


def _c_sunburst(spec, rows, opt):
    import math
    roots = _csv_tree(rows, opt) if spec is None else _tree_from(spec.get("nodes") or [])
    n = sum(1 for _ in _walk_tree(roots))
    _cap(spec, n, 40, "nodes", opt["unbounded"])
    depth = _depth(roots)
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 420, ox=30, right=30, bottom=30)
    cx, cy = W / 2, oy + ph / 2 + 8
    ring = min(pw, ph) * 0.42 / max(depth, 1)
    pal = series_palette(t)

    def walk(node, a0, a1, d, color):
        if d == 0 and len(roots) == 1:
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{ring * 0.85:.1f}" fill="{color}"/>')
            parts.append(
                f'<text x="{cx:.1f}" y="{cy + 4:.1f}" font-size="12" font-family="{FONT}" fill="{t["card"]}" text-anchor="middle">{esc(_short(node["name"], 12))}</text>')
        else:
            r0 = ring * (d if len(roots) == 1 else d + 0.15)
            r1 = r0 + ring * 0.92
            if a1 - a0 >= math.tau - 1e-3:
                parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r1:.1f}" fill="{color}"/>')
                parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r0:.1f}" fill="{t["paper"]}"/>')
            else:
                parts.append(f'<path d="{_annulus(cx, cy, r0, r1, a0, a1)}" fill="{color}" stroke="{t["paper"]}" stroke-width="1"/>')
            if a1 - a0 > 0.35:
                mid = (a0 + a1) / 2
                rr = (r0 + r1) / 2 if d else ring * 0.4
                parts.append(
                    f'<text x="{cx + rr * math.cos(mid):.1f}" y="{cy + rr * math.sin(mid) + 3:.1f}" font-size="10" font-family="{FONT}" fill="{t["card"]}" text-anchor="middle">{esc(_short(node["name"], 10))}</text>')
        kids = node["children"]
        if not kids:
            return
        total = sum(c["val"] for c in kids) or 1
        ang = a0
        for i, child in enumerate(kids):
            span = (a1 - a0) * child["val"] / total
            walk(child, ang, ang + span, d + 1, pal[(d + i) % len(pal)])
            ang += span

    total = sum(r["val"] for r in roots) or 1
    ang = -math.pi / 2
    for i, root in enumerate(roots):
        span = math.tau * root["val"] / total
        walk(root, ang, ang + span, 0, pal[i % len(pal)])
        ang += span
    return _done(parts, opt, W, H, n)


def _c_heatmap(spec, rows, opt):
    c = _need(rows, [("x", opt["x"]), ("y", opt["y"]), ("val", opt["val"])])
    xs, ys = [], []
    cell = {}
    for r in rows:
        try:
            x, y, v = str(r.get(c["x"]) or ""), str(r.get(c["y"]) or ""), _f(r, c["val"])
        except (TypeError, ValueError):
            continue
        if x not in xs:
            xs.append(x)
        if y not in ys:
            ys.append(y)
        cell[(x, y)] = v
    if not xs or not ys:
        raise SystemExit("heatmap needs x, y, and val")
    _cap(None, len(xs) * len(ys), 400, "cells", opt["unbounded"])
    vals = list(cell.values())
    lo, hi = min(vals), max(vals)
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, max(240, len(ys) * 36 + 20), ox=110, bottom=78)
    cw, ch = pw / len(xs), ph / len(ys)
    show = len(xs) * len(ys) <= 48 and opt["markers"]
    for iy, y in enumerate(ys):
        parts.append(
            f'<text x="{ox - 8}" y="{oy + (iy + 0.5) * ch + 3:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="end">{esc(_short(y, 14))}</text>')
        for ix, x in enumerate(xs):
            if (x, y) not in cell:
                continue
            v = cell[(x, y)]
            u = 0.5 if hi == lo else (v - lo) / (hi - lo)
            parts.append(
                f'<rect x="{ox + ix * cw + 1:.1f}" y="{oy + iy * ch + 1:.1f}" width="{cw - 2:.1f}" height="{ch - 2:.1f}" fill="{_heat_color(t, u)}"/>')
            if show and cw > 28 and ch > 16:
                ink = t["ink"] if u < 0.45 else t["card"]
                parts.append(
                    f'<text x="{ox + (ix + 0.5) * cw:.1f}" y="{oy + (iy + 0.5) * ch + 3:.1f}" font-size="10" font-family="{FONT}" fill="{ink}" text-anchor="middle">{fmt_tick(v)}</text>')
    _cat_labels(parts, t, xs, [ox + (i + 0.5) * cw for i in range(len(xs))], oy + ph + 16, len(xs) > 6)
    _ramp(parts, t, ox, H - 40, 140, fmt_tick(lo), fmt_tick(hi))
    return _done(parts, opt, W, H, len(cell))


def _c_calendar(spec, rows, opt):
    import datetime
    c = _need(rows, [("date", opt["x"]), ("val", opt["val"] or opt["y"])])
    pts = []
    for r in rows:
        d = _parse_date(r.get(c["date"]))
        if d is None:
            continue
        try:
            pts.append((d.date(), _f(r, c["val"])))
        except (TypeError, ValueError):
            continue
    if not pts:
        raise SystemExit("calendar needs dates and values")
    pts.sort()
    end = pts[-1][0]
    start = end - datetime.timedelta(weeks=59)
    window = [p for p in pts if p[0] >= start]
    note = "" if len(window) == len(pts) else f"from {window[0][0].isoformat()}"
    vals = [v for _, v in window]
    lo, hi = min(vals), max(vals)
    by = {d: v for d, v in window}
    first = window[0][0] - datetime.timedelta(days=window[0][0].weekday())
    last = window[-1][0]
    weeks = (last - first).days // 7 + 1
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 220, ox=48, right=28, W=max(760, 70 + weeks * 16), bottom=64)
    cell = 14
    days = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    for i, name in enumerate(days):
        parts.append(
            f'<text x="{ox - 4}" y="{oy + i * (cell + 3) + 11:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">{name[0]}</text>')
    for d, v in by.items():
        week = (d - first).days // 7
        dow = d.weekday()
        u = 0.5 if hi == lo else (v - lo) / (hi - lo)
        parts.append(
            f'<rect x="{ox + week * (cell + 3):.1f}" y="{oy + dow * (cell + 3):.1f}" width="{cell}" height="{cell}" rx="2" fill="{_heat_color(t, u)}"/>')
    _ramp(parts, t, ox, oy + 7 * (cell + 3) + 8, 120, fmt_tick(lo), fmt_tick(hi))
    return _done(parts, opt, W, H, len(window), note)


def _c_radar(spec, rows, opt):
    import math
    c = _need(rows, [("axis", opt["x"] or opt["label"]), ("series", opt["group"]), ("val", opt["val"] or opt["y"])])
    axes, series = [], []
    cell = {}
    for r in rows:
        try:
            axis, name, val = str(r.get(c["axis"]) or ""), str(r.get(c["series"]) or ""), _f(r, c["val"])
        except (TypeError, ValueError):
            continue
        if axis not in axes:
            axes.append(axis)
        if name not in series:
            series.append(name)
        cell[(axis, name)] = val
    if len(axes) < 3:
        raise SystemExit("radar needs at least 3 axes")
    _cap(None, len(axes), 8, "axes", opt["unbounded"])
    _cap(None, len(series), 4, "series", opt["unbounded"])
    vals = list(cell.values())
    lo, hi = _domain(vals)
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 380, ox=40, right=40, bottom=70)
    cx, cy = W / 2, oy + ph / 2
    radius = min(pw, ph) * 0.38
    pal = series_palette(t)
    for step in (0.25, 0.5, 0.75, 1):
        pts = []
        for i in range(len(axes)):
            ang = -math.pi / 2 + i * math.tau / len(axes)
            pts.append(f"{cx + radius * step * math.cos(ang):.1f},{cy + radius * step * math.sin(ang):.1f}")
        parts.append(f'<polygon points="{" ".join(pts)}" fill="none" stroke="{t["rule"]}"/>')
    for i, axis in enumerate(axes):
        ang = -math.pi / 2 + i * math.tau / len(axes)
        x, y = cx + radius * math.cos(ang), cy + radius * math.sin(ang)
        parts.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="{t["rule"]}"/>')
        lx, ly = cx + (radius + 16) * math.cos(ang), cy + (radius + 16) * math.sin(ang)
        anchor = "middle" if abs(math.cos(ang)) < 0.3 else ("start" if math.cos(ang) > 0 else "end")
        parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="{anchor}">{esc(_short(axis, 14))}</text>')
    for s, name in enumerate(series):
        pts = []
        col = t["accent"] if _hit(opt["highlights"], name) else (t["link"] if len(series) == 1 else pal[s % len(pal)])
        for i, axis in enumerate(axes):
            v = cell.get((axis, name), lo)
            u = 0 if hi == lo else (v - lo) / (hi - lo)
            ang = -math.pi / 2 + i * math.tau / len(axes)
            pts.append((cx + radius * u * math.cos(ang), cy + radius * u * math.sin(ang)))
        seq = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        parts.append(f'<polygon points="{seq}" fill="{col}" fill-opacity="0.16" stroke="{col}" stroke-width="1.6"/>')
        if opt["markers"] or _hit(opt["highlights"], name):
            for x, y in pts:
                _dot(parts, t, x, y, 3.2, col, True, _hit(opt["highlights"], name))
    if len(series) > 1:
        _legend(parts, t, [(pal[i % len(pal)], n) for i, n in enumerate(series)], ox, H - 34)
    return _done(parts, opt, W, H, len(cell))


def _c_polar(spec, rows, opt):
    import math
    c = _need(rows, [("cat", opt["label"] or opt["x"]), ("val", opt["val"] or opt["y"])])
    items = []
    for r in rows:
        try:
            items.append((str(r.get(c["cat"]) or ""), max(0.0, _f(r, c["val"]))))
        except (TypeError, ValueError):
            continue
    if not items:
        raise SystemExit("polar needs cat and val")
    _cap(None, len(items), 24, "slices", opt["unbounded"])
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 380, ox=36, right=36)
    cx, cy = W / 2, oy + ph / 2
    radius = min(pw, ph) * 0.40
    peak = max(v for _, v in items) or 1
    for step in (0.5, 1):
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius * step:.1f}" fill="none" stroke="{t["rule"]}"/>')
    for i, (name, val) in enumerate(items):
        a0 = -math.pi / 2 + i * math.tau / len(items)
        a1 = a0 + math.tau / len(items)
        r = radius * val / peak
        col = t["accent"] if _hit(opt["highlights"], name) else t["link"]
        if a1 - a0 >= math.tau - 1e-3:
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{col}" fill-opacity="0.8"/>')
        else:
            x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
            x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
            large = 1 if a1 - a0 > math.pi else 0
            parts.append(
                f'<path d="M {cx:.1f} {cy:.1f} L {x0:.1f} {y0:.1f} A {r:.1f} {r:.1f} 0 {large} 1 {x1:.1f} {y1:.1f} Z" fill="{col}" fill-opacity="0.8" stroke="{t["paper"]}"/>')
        mid = (a0 + a1) / 2
        parts.append(
            f'<text x="{cx + (radius + 14) * math.cos(mid):.1f}" y="{cy + (radius + 14) * math.sin(mid):.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(name, 12))}</text>')
    return _done(parts, opt, W, H, len(items))


def _c_status(spec, rows, opt):
    c = _need(rows, [("row", opt["y"] or opt["label"]), ("col", opt["x"]), ("state", opt["group"] or opt["val"])])
    rs, cs = [], []
    cell = {}
    for r in rows:
        row, col, state = str(r.get(c["row"]) or ""), str(r.get(c["col"]) or ""), str(r.get(c["state"]) or "").lower()
        if row not in rs:
            rs.append(row)
        if col not in cs:
            cs.append(col)
        cell[(row, col)] = state
    _cap(None, len(rs) * max(len(cs), 1), 200, "cells", opt["unbounded"])
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, max(200, len(rs) * 36 + 10), ox=120, bottom=70)
    cw = pw / max(len(cs), 1)
    ch = ph / max(len(rs), 1)
    paint = {"ok": t["link"], "up": t["link"], "good": t["link"], "warn": t["accent"], "warning": t["accent"],
             "down": t["ink"], "bad": t["ink"], "fail": t["ink"], "failed": t["ink"]}
    for iy, row in enumerate(rs):
        parts.append(
            f'<text x="{ox - 8}" y="{oy + (iy + 0.5) * ch + 4:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="end">{esc(_short(row, 16))}</text>')
        for ix, col in enumerate(cs):
            state = cell.get((row, col), "")
            colr = paint.get(state, t["card"])
            stroke = t["accent"] if _hit(opt["highlights"], row, col, state) else t["rule"]
            parts.append(
                f'<rect x="{ox + ix * cw + 3:.1f}" y="{oy + iy * ch + 3:.1f}" width="{cw - 6:.1f}" height="{ch - 6:.1f}" rx="3" fill="{colr}" stroke="{stroke}"/>')
    _cat_labels(parts, t, cs, [ox + (i + 0.5) * cw for i in range(len(cs))], oy + ph + 16, len(cs) > 6)
    _legend(parts, t, [(t["link"], "ok"), (t["accent"], "warn"), (t["ink"], "down"), (t["card"], "other")], ox, H - 34)
    return _done(parts, opt, W, H, len(cell))


def _c_forest(spec, rows, opt):
    c = _need(rows, [("cat", opt["label"] or opt["x"]), ("est", opt["val"] or opt["y"]), ("lo", opt["lo"]), ("hi", opt["hi"])])
    items = []
    for r in rows:
        try:
            items.append((str(r.get(c["cat"]) or ""), _f(r, c["est"]), _f(r, c["lo"]), _f(r, c["hi"])))
        except (TypeError, ValueError):
            continue
    if not items:
        raise SystemExit("forest needs cat, est, lo, and hi")
    _cap(None, len(items), 20, "rows", opt["unbounded"])
    vals = [v for _, e, lo, hi in items for v in (e, lo, hi)]
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, max(220, len(items) * 28), ox=140)
    xt = nice_ticks(min(vals), max(vals) if max(vals) != min(vals) else min(vals) + 1)
    span = (xt[-1] - xt[0]) or 1

    def X(v):
        return ox + (v - xt[0]) / span * pw

    parts.append(f'<line x1="{ox}" y1="{oy + ph}" x2="{ox + pw}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    for v in xt:
        x = X(v)
        if opt["grid"]:
            parts.append(f'<line x1="{x:.1f}" y1="{oy}" x2="{x:.1f}" y2="{oy + ph}" stroke="{t["rule"]}"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{oy + ph + 16}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="middle">{fmt_tick(v)}</text>')
    if xt[0] <= 0 <= xt[-1]:
        parts.append(f'<line x1="{X(0):.1f}" y1="{oy}" x2="{X(0):.1f}" y2="{oy + ph}" stroke="{t["soft"]}" stroke-dasharray="3 3"/>')
    for i, (name, est, lo, hi) in enumerate(items):
        y = oy + (i + 0.5) * ph / len(items)
        hit = _hit(opt["highlights"], name)
        col = t["accent"] if hit else t["link"]
        parts.append(f'<line x1="{X(lo):.1f}" y1="{y:.1f}" x2="{X(hi):.1f}" y2="{y:.1f}" stroke="{col}" stroke-width="1.4"/>')
        parts.append(f'<line x1="{X(lo):.1f}" y1="{y - 4:.1f}" x2="{X(lo):.1f}" y2="{y + 4:.1f}" stroke="{col}"/>')
        parts.append(f'<line x1="{X(hi):.1f}" y1="{y - 4:.1f}" x2="{X(hi):.1f}" y2="{y + 4:.1f}" stroke="{col}"/>')
        _dot(parts, t, X(est), y, 4.2, col, True, hit)
        parts.append(
            f'<text x="{ox - 8}" y="{y + 3:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="end">{esc(_short(name, 18))}</text>')
    return _done(parts, opt, W, H, len(items))


def _c_qq(spec, rows, opt):
    c = _need(rows, [("val", opt["val"] or opt["y"] or opt["x"])])
    vals = sorted(v for _, v in _floats(rows, c["val"]))
    _cap(None, len(vals), 400, "points", opt["unbounded"])
    n = len(vals)
    theo = [_ninv((i + 0.5) / n) for i in range(n)]
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 320)
    X, Y = _axes(parts, t, ox, oy, pw, ph, nice_ticks(min(theo), max(theo)), nice_ticks(*_domain(vals, floor0=False)), opt["grid"])
    q1, _, q3 = _quartiles(vals)
    t1, t3 = _ninv(0.25), _ninv(0.75)
    if t3 != t1:
        slope = (q3 - q1) / (t3 - t1)
        intercept = q1 - slope * t1
        x0, x1 = min(theo), max(theo)
        parts.append(
            f'<line x1="{X(x0):.1f}" y1="{Y(intercept + slope * x0):.1f}" x2="{X(x1):.1f}" y2="{Y(intercept + slope * x1):.1f}" stroke="{t["accent"]}" stroke-width="1.2"/>')
    for x, y in zip(theo, vals):
        _dot(parts, t, X(x), Y(y), 3.2, t["link"], opt["markers"], False)
    return _done(parts, opt, W, H, n, "normal quantile")


def _c_volcano(spec, rows, opt):
    import math
    c = _need(rows, [("x", opt["x"]), ("y", opt["y"])])
    lab = _col(rows, opt["label"], "label")
    pts = []
    for r in rows:
        try:
            pts.append((r, _f(r, c["x"]), _f(r, c["y"])))
        except (TypeError, ValueError):
            continue
    if not pts:
        raise SystemExit("volcano needs numeric x and y")
    _cap(None, len(pts), 400, "points", opt["unbounded"])
    plotted = []
    as_p = max(p[2] for p in pts) <= 1
    for r, x, y in pts:
        py = -math.log10(max(y, 1e-300)) if as_p else y
        plotted.append((r, x, py))
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 320, bottom=56)
    xs = [p[1] for p in plotted]
    ys = [p[2] for p in plotted]
    X, Y = _axes(parts, t, ox, oy, pw, ph, nice_ticks(min(xs), max(xs) if max(xs) != min(xs) else min(xs) + 1),
                 nice_ticks(0, max(ys) if max(ys) else 1), opt["grid"])
    ranked = sorted(plotted, key=lambda p: p[2], reverse=True)
    label_ids = {id(p[0]) for p in ranked[:5]}
    for r, x, y in plotted:
        name = str(r.get(lab) or "") if lab else ""
        strong = abs(x) > 1 and y > 2
        hit = _hit(opt["highlights"], name, x) or strong
        _dot(parts, t, X(x), Y(y), 3.4, t["link"], opt["markers"], hit)
        if opt["markers"] and lab and id(r) in label_ids and name:
            parts.append(
                f'<text x="{X(x) + 6:.1f}" y="{Y(y) - 4:.1f}" font-size="10" font-family="{FONT}" fill="{t["ink"]}">{esc(_short(name, 16))}</text>')
    note = "y is -log10 of a p-value" if as_p else ""
    return _done(parts, opt, W, H, len(plotted), note)

def _c_candle(spec, rows, opt):
    c = _need(rows, [("x", opt["x"]), ("open", None), ("high", None), ("low", None), ("close", None)])
    items = []
    for r in rows:
        try:
            items.append((str(r.get(c["x"]) or ""), _f(r, c["open"]), _f(r, c["high"]), _f(r, c["low"]), _f(r, c["close"])))
        except (TypeError, ValueError):
            continue
    if not items:
        raise SystemExit("candle needs x, open, high, low, close")
    _cap(None, len(items), 80, "candles", opt["unbounded"])
    vals = [v for it in items for v in it[2:4]]
    rotate = len(items) > 8
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 300, bottom=84 if rotate else 56)
    yt = nice_ticks(*_domain(vals, floor0=min(vals) >= 0))
    span = (yt[-1] - yt[0]) or 1

    def Y(v):
        return oy + ph - (v - yt[0]) / span * ph

    parts.append(f'<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    parts.append(f'<line x1="{ox}" y1="{oy + ph}" x2="{ox + pw}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    for v in yt:
        y = Y(v)
        if opt["grid"]:
            parts.append(f'<line x1="{ox}" y1="{y:.1f}" x2="{ox + pw}" y2="{y:.1f}" stroke="{t["rule"]}"/>')
        parts.append(
            f'<text x="{ox - 8}" y="{y + 3:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">{fmt_tick(v)}</text>')
    slot = pw / len(items)
    bw = min(14, slot * 0.5)
    centers = []
    for i, (name, o, h, low, cl) in enumerate(items):
        x = ox + (i + 0.5) * slot
        centers.append(x)
        col = t["accent"] if _hit(opt["highlights"], name) or cl < o else t["link"]
        parts.append(f'<line x1="{x:.1f}" y1="{Y(h):.1f}" x2="{x:.1f}" y2="{Y(low):.1f}" stroke="{col}" stroke-width="1.2"/>')
        top, bot = Y(max(o, cl)), Y(min(o, cl))
        parts.append(
            f'<rect x="{x - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(1.2, bot - top):.1f}" fill="{col}"/>')
    _cat_labels(parts, t, [it[0] for it in items], centers, oy + ph + 16, rotate)
    return _done(parts, opt, W, H, len(items))


def _sankey_layers(links):
    """Longest-path columns. A cycle does not add another column."""
    names = []
    pred = {}
    for s, d, _v in links:
        if s not in pred:
            pred[s] = []
            names.append(s)
        if d not in pred:
            pred[d] = []
            names.append(d)
        if s not in pred[d]:
            pred[d].append(s)
    rank = {n: 0 for n in names}
    guard = len(names)
    for _ in range(guard):
        changed = False
        for n in names:
            ups = [rank[p] + 1 for p in pred[n]]
            if not ups:
                continue
            nxt = max(ups)
            if nxt >= guard or nxt == rank[n]:
                continue
            rank[n] = nxt
            changed = True
        if not changed:
            break
    layers = {}
    for n in names:
        layers.setdefault(rank[n], []).append(n)
    return [layers[k] for k in sorted(layers)]


def _sankey_balance(cols, links):
    """Reorder each column so flows that share a node stay in the same top-to-bottom order."""
    pred, succ = {}, {}
    for s, d, v in links:
        pred.setdefault(d, []).append((s, v))
        succ.setdefault(s, []).append((d, v))
    cols = [list(c) for c in cols]

    def bary(group, neigh, index):
        def key(n):
            ws = [(index[m], w) for m, w in neigh.get(n, []) if m in index]
            if not ws:
                return (index.get(n, 0), n)
            tot = sum(w for _, w in ws) or 1
            return (sum(i * w for i, w in ws) / tot, n)
        return sorted(group, key=key)

    for _ in range(6):
        index = {n: i for col in cols for i, n in enumerate(col)}
        cols = [cols[0]] + [bary(col, pred, index) for col in cols[1:]]
        index = {n: i for col in cols for i, n in enumerate(col)}
        cols = [bary(col, succ, index) for col in cols[:-1]] + [cols[-1]]
    return cols


def _c_sankey(spec, rows, opt):
    c = _need(rows, [("src", opt["x"] or opt["label"]), ("dst", opt["y"]), ("val", opt["val"])])
    links = []
    for r in rows:
        try:
            val = _f(r, c["val"])
        except (TypeError, ValueError):
            continue
        if val <= 0:
            continue
        links.append((str(r.get(c["src"]) or ""), str(r.get(c["dst"]) or ""), val))
    if not links:
        raise SystemExit("sankey needs src, dst, and val")
    _cap(None, len(links), 40, "links", opt["unbounded"])
    out_w, in_w = {}, {}
    for s, d, v in links:
        out_w[s] = out_w.get(s, 0) + v
        in_w[d] = in_w.get(d, 0) + v
    cols = _sankey_balance(_sankey_layers(links), links)
    names = [n for col in cols for n in col]
    weight = {n: max(out_w.get(n, 0), in_w.get(n, 0)) for n in names}
    nw, gap = 12, 12
    n_cols = len(cols)
    W = max(780, 160 + n_cols * 230)
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 380, ox=132, right=132, W=W, bottom=48)
    if n_cols == 1:
        xs = [ox + pw / 2 - nw / 2]
    else:
        xs = [ox + i * (pw - nw) / (n_cols - 1) for i in range(n_cols)]

    def pads(ci):
        return (6, 6)

    ks = []
    for ci, col in enumerate(cols):
        top_pad, bot_pad = pads(ci)
        gaps = gap * max(len(col) - 1, 0)
        total = sum(weight[n] for n in col) or 1
        ks.append(max(0.0, (ph - top_pad - bot_pad - gaps) / total))
    k = min(ks) if ks else 1
    top, height = {}, {}
    for ci, col in enumerate(cols):
        top_pad, bot_pad = pads(ci)
        raw = [weight[n] * k for n in col]
        boost = sum(max(0.0, 4 - h) for h in raw)
        gaps = gap * max(len(col) - 1, 0)
        room = ph - top_pad - bot_pad - gaps
        use = [max(4.0, h) for h in raw] if sum(raw) + boost <= room + 0.1 else [max(2.0, h) for h in raw]
        extra = max(0.0, room - sum(use))
        y = oy + top_pad + extra / 2
        for n, h in zip(col, use):
            top[n] = y
            height[n] = h
            y += h + gap
    col_of = {n: ci for ci, col in enumerate(cols) for n in col}
    index = {n: i for col in cols for i, n in enumerate(col)}
    outgoing = {n: [] for n in names}
    incoming = {n: [] for n in names}
    for i, (s, d, _v) in enumerate(links):
        outgoing[s].append(i)
        incoming[d].append(i)

    def sort_out(idxs):
        return sorted(idxs, key=lambda i: (col_of[links[i][1]], index[links[i][1]], links[i][1]))

    def sort_in(idxs):
        return sorted(idxs, key=lambda i: (col_of[links[i][0]], index[links[i][0]], links[i][0]))

    src_box, dst_box = {}, {}
    for n in names:
        y = top[n]
        share = weight[n] or 1
        for i in sort_out(outgoing[n]):
            h = height[n] * (links[i][2] / share)
            src_box[i] = (y, y + h)
            y += h
        y = top[n]
        for i in sort_in(incoming[n]):
            h = height[n] * (links[i][2] / share)
            dst_box[i] = (y, y + h)
            y += h
    sources = [n for n in names if out_w.get(n, 0) > 0]
    pal = series_palette(t)
    if len(sources) <= 1:
        src_color = {n: t["link"] for n in sources}
    else:
        src_color = {n: pal[i % len(pal)] for i, n in enumerate(sources)}

    def ribbon(x1, y1a, y1b, x2, y2a, y2b):
        if y1b - y1a > 7:
            y1a, y1b = y1a + 1.2, y1b - 1.2
        if y2b - y2a > 7:
            y2a, y2b = y2a + 1.2, y2b - 1.2
        mx = (x1 + x2) / 2
        return (
            f"M {x1:.1f} {y1a:.1f} C {mx:.1f} {y1a:.1f} {mx:.1f} {y2a:.1f} {x2:.1f} {y2a:.1f} "
            f"L {x2:.1f} {y2b:.1f} C {mx:.1f} {y2b:.1f} {mx:.1f} {y1b:.1f} {x1:.1f} {y1b:.1f} Z")

    def attach(s, d):
        cs, cd = col_of[s], col_of[d]
        if cs < cd:
            return xs[cs] + nw, xs[cd]
        if cs > cd:
            return xs[cs], xs[cd] + nw
        return xs[cs] + nw, xs[cs] + nw + 48

    order = sorted(range(len(links)), key=lambda i: 1 if _hit(opt["highlights"], links[i][0], links[i][1]) else 0)
    for i in order:
        s, d, _v = links[i]
        x1, x2 = attach(s, d)
        y1a, y1b = src_box[i]
        y2a, y2b = dst_box[i]
        hit = _hit(opt["highlights"], s, d)
        colr = t["accent"] if hit else src_color.get(s, t["link"])
        parts.append(
            f'<path d="{ribbon(x1, y1a, y1b, x2, y2a, y2b)}" fill="{colr}" fill-opacity="0.9" stroke="{t["paper"]}" stroke-width="1.2"/>')
    for ci, col in enumerate(cols):
        x = xs[ci]
        for j, n in enumerate(col):
            y0, h = top[n], height[n]
            parts.append(f'<rect x="{x:.1f}" y="{y0:.1f}" width="{nw}" height="{h:.1f}" fill="{t["ink"]}"/>')
            shown = esc(_short(n, 18))
            if ci == 0 or ci == n_cols - 1:
                anchor = "end" if ci == 0 else "start"
                lx = x - 10 if ci == 0 else x + nw + 10
                parts.append(
                    f'<text x="{lx:.1f}" y="{y0 + h / 2 + 4:.1f}" font-size="12" font-family="{FONT}" fill="{t["ink"]}" text-anchor="{anchor}">{shown}</text>')
                if opt["markers"] and h >= 28:
                    parts.append(
                        f'<text x="{lx:.1f}" y="{y0 + h / 2 + 18:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="{anchor}">{esc(fmt_tick(weight[n]))}</text>')
            else:
                parts.append(
                    f'<text x="{x + nw / 2:.1f}" y="{y0 + h / 2 + 4:.1f}" font-size="12" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle" stroke="{t["paper"]}" stroke-width="3.5" paint-order="stroke fill">{shown}</text>')
    return _done(parts, opt, W, H, len(links))


def _c_stream(spec, rows, opt):
    c = _need(rows, [("x", opt["x"]), ("group", opt["group"]), ("val", opt["val"] or opt["y"])])
    xs, groups, cell = [], [], {}
    for r in rows:
        try:
            x, g, v = str(r.get(c["x"]) or ""), str(r.get(c["group"]) or ""), _f(r, c["val"])
        except (TypeError, ValueError):
            continue
        if x not in xs:
            xs.append(x)
        if g not in groups:
            groups.append(g)
        cell[(x, g)] = cell.get((x, g), 0) + max(0.0, v)
    if len(xs) < 2 or not groups:
        raise SystemExit("stream needs at least two x values and a group")
    _cap(None, len(groups), 8, "groups", opt["unbounded"])
    totals = [sum(cell.get((x, g), 0) for g in groups) for x in xs]
    peak = max(totals) or 1
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 300, bottom=72)
    pal = series_palette(t)

    def X(i):
        return ox + i * pw / (len(xs) - 1)

    def Y(v):
        return oy + ph / 2 - v / peak * (ph * 0.86)

    def smooth(pts):
        """Closed-enough cubic through a polyline. Endpoints stay put."""
        if len(pts) < 2:
            return ""
        seq = [pts[0]]
        for i in range(len(pts) - 1):
            p0 = pts[i - 1] if i else pts[i]
            p1, p2 = pts[i], pts[i + 1]
            p3 = pts[i + 2] if i + 2 < len(pts) else pts[i + 1]
            c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
            c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
            seq.append(c1)
            seq.append(c2)
            seq.append(p2)
        head = f"M {seq[0][0]:.1f} {seq[0][1]:.1f}"
        body = []
        for i in range(1, len(seq), 3):
            a, b, c = seq[i], seq[i + 1], seq[i + 2]
            body.append(f"C {a[0]:.1f} {a[1]:.1f} {b[0]:.1f} {b[1]:.1f} {c[0]:.1f} {c[1]:.1f}")
        return head + " " + " ".join(body)

    low = [-t / 2 for t in totals]
    for gi, g in enumerate(groups):
        high = [low[i] + cell.get((xs[i], g), 0) for i in range(len(xs))]
        fwd = [(X(i), Y(low[i])) for i in range(len(xs))]
        back = [(X(i), Y(high[i])) for i in range(len(xs) - 1, -1, -1)]
        col = pal[gi % len(pal)]
        parts.append(f'<path d="{smooth(fwd)} {smooth(back).replace("M", "L", 1)} Z" fill="{col}" fill-opacity="0.82"/>')
        low = high
    _cat_labels(parts, t, xs, [X(i) for i in range(len(xs))], oy + ph + 16, len(xs) > 6)
    _legend(parts, t, [(pal[i % len(pal)], g) for i, g in enumerate(groups)], ox, H - 34)
    return _done(parts, opt, W, H, len(xs) * len(groups))


def _c_funnel(spec, rows, opt):
    c = _need(rows, [("cat", opt["label"] or opt["x"]), ("val", opt["val"] or opt["y"])])
    items = _shares(rows, c["cat"], c["val"])
    _cap(None, len(items), 8, "stages", opt["unbounded"])
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, max(240, len(items) * 56), ox=120, right=80)
    first = items[0][1] or 1
    band = ph / len(items)
    cx = ox + pw / 2
    prev = items[0][1]
    for i, (name, val) in enumerate(items):
        w0 = pw * (prev / first)
        w1 = pw * (val / first)
        y0 = oy + i * band
        y1 = y0 + band - 8
        col = t["accent"] if _hit(opt["highlights"], name) else t["link"]
        parts.append(
            f'<polygon points="{cx - w0 / 2:.1f},{y0:.1f} {cx + w0 / 2:.1f},{y0:.1f} {cx + w1 / 2:.1f},{y1:.1f} {cx - w1 / 2:.1f},{y1:.1f}" fill="{col}" fill-opacity="{0.9 - i * 0.08:.2f}"/>')
        parts.append(
            f'<text x="{ox - 8}" y="{(y0 + y1) / 2 + 4:.1f}" font-size="12" font-family="{FONT}" fill="{t["ink"]}" text-anchor="end">{esc(_short(name, 16))}</text>')
        if opt["markers"]:
            parts.append(
                f'<text x="{cx:.1f}" y="{(y0 + y1) / 2 + 4:.1f}" font-size="12" font-family="{FONT}" fill="{t["card"]}" text-anchor="middle">{val / first * 100:.0f}%</text>')
        prev = val
    return _done(parts, opt, W, H, len(items))


def _c_combo(spec, rows, opt):
    c = _need(rows, [("x", opt["x"]), ("bar", opt["a"] or opt["val"]), ("line", opt["b"] or opt["y"])])
    items = []
    for r in rows:
        try:
            items.append((str(r.get(c["x"]) or ""), _f(r, c["bar"]), _f(r, c["line"])))
        except (TypeError, ValueError):
            continue
    if not items:
        raise SystemExit("combo needs x, bar, and line")
    _cap(None, len(items), 24, "points", opt["unbounded"])
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 300, right=72, bottom=76)
    bars = [b for _, b, _ in items]
    lines = [v for _, _, v in items]
    y0 = axis_ticks(*_domain(bars))
    y1 = nice_ticks(*_domain(lines))
    s0 = (y0[-1] - y0[0]) or 1
    s1 = (y1[-1] - y1[0]) or 1

    def Y0(v):
        return oy + ph - (v - y0[0]) / s0 * ph

    def Y1(v):
        return oy + ph - (v - y1[0]) / s1 * ph

    parts.append(f'<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    parts.append(f'<line x1="{ox + pw}" y1="{oy}" x2="{ox + pw}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    parts.append(f'<line x1="{ox}" y1="{oy + ph}" x2="{ox + pw}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    for v in y0:
        y = Y0(v)
        if opt["grid"]:
            parts.append(f'<line x1="{ox}" y1="{y:.1f}" x2="{ox + pw}" y2="{y:.1f}" stroke="{t["rule"]}"/>')
        parts.append(
            f'<text x="{ox - 8}" y="{y + 3:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">{fmt_tick(v)}</text>')
    for v in y1:
        parts.append(
            f'<text x="{ox + pw + 8}" y="{Y1(v) + 3:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}">{fmt_tick(v)}</text>')
    slot = pw / len(items)
    bw = min(28, slot * 0.5)
    centers = []
    d = []
    for i, (name, bar, line) in enumerate(items):
        x = ox + (i + 0.5) * slot
        centers.append(x)
        top = Y0(max(bar, 0))
        parts.append(
            f'<rect x="{x - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(1, oy + ph - top):.1f}" fill="{t["link"]}" fill-opacity="0.85"/>')
        d.append(f'{"M" if i == 0 else "L"} {x:.1f} {Y1(line):.1f}')
    parts.append(f'<path d="{" ".join(d)}" fill="none" stroke="{t["accent"]}" stroke-width="1.8"/>')
    if opt["markers"]:
        for i, (name, bar, line) in enumerate(items):
            _dot(parts, t, centers[i], Y1(line), 3.4, t["accent"], True, _hit(opt["highlights"], name))
    _cat_labels(parts, t, [it[0] for it in items], centers, oy + ph + 16, len(items) > 6)
    _legend(parts, t, [(t["link"], "bar"), (t["accent"], "line")], ox, H - 34)
    return _done(parts, opt, W, H, len(items))


def _c_quadrant(spec, rows, opt):
    c = _need(rows, [("x", opt["x"]), ("y", opt["y"])])
    lab = _col(rows, opt["label"], "label")
    pts = []
    for r in rows:
        try:
            pts.append((str(r.get(lab) or "") if lab else "", _f(r, c["x"]), _f(r, c["y"])))
        except (TypeError, ValueError):
            continue
    if not pts:
        raise SystemExit("quadrant needs numeric x and y")
    _cap(None, len(pts), 40, "points", opt["unbounded"])
    xs = [p[1] for p in pts]
    ys = [p[2] for p in pts]
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 320, bottom=56)
    xt = nice_ticks(min(xs), max(xs) if max(xs) != min(xs) else min(xs) + 1)
    yt = nice_ticks(min(ys), max(ys) if max(ys) != min(ys) else min(ys) + 1)
    X, Y = _axes(parts, t, ox, oy, pw, ph, xt, yt, opt["grid"])

    def mid(vals, ticks):
        if min(vals) < 0 < max(vals):
            return 0.0
        return _quartiles(vals)[1]

    mx, my = mid(xs, xt), mid(ys, yt)
    parts.append(f'<line x1="{X(mx):.1f}" y1="{oy}" x2="{X(mx):.1f}" y2="{oy + ph}" stroke="{t["soft"]}" stroke-dasharray="4 3"/>')
    parts.append(f'<line x1="{ox}" y1="{Y(my):.1f}" x2="{ox + pw}" y2="{Y(my):.1f}" stroke="{t["soft"]}" stroke-dasharray="4 3"/>')
    for name, x, y in pts:
        _dot(parts, t, X(x), Y(y), 4.2, t["link"], opt["markers"], _hit(opt["highlights"], name))
        if name and (opt["markers"] or len(pts) <= 12):
            tx = min(ox + pw - 4, X(x) + 8)
            parts.append(
                f'<text x="{tx:.1f}" y="{Y(y) - 6:.1f}" font-size="10" font-family="{FONT}" fill="{t["ink"]}">{esc(_short(name, 18))}</text>')
    return _done(parts, opt, W, H, len(pts))


def _isolines(xs, ys, grid, levels):
    segs = []
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            corners = []
            ok = True
            for dj, di in ((0, 0), (0, 1), (1, 1), (1, 0)):
                z = grid[j + dj][i + di]
                if z is None:
                    ok = False
                    break
                corners.append((xs[i + di], ys[j + dj], z))
            if not ok:
                continue
            for level in levels:
                hits = []
                for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
                    za, zb = corners[a][2], corners[b][2]
                    if (za - level) == 0 and (zb - level) == 0:
                        continue
                    if (za - level) * (zb - level) < 0:
                        t = (level - za) / (zb - za)
                        hits.append((corners[a][0] + t * (corners[b][0] - corners[a][0]),
                                     corners[a][1] + t * (corners[b][1] - corners[a][1])))
                if len(hits) >= 2:
                    segs.append((hits[0], hits[1], level))
                if len(hits) == 4:
                    segs.append((hits[2], hits[3], level))
    return segs


def _c_contour(spec, rows, opt):
    c = _need(rows, [("x", opt["x"]), ("y", opt["y"]), ("z", opt["val"])])
    pts = []
    for r in rows:
        try:
            pts.append((_f(r, c["x"]), _f(r, c["y"]), _f(r, c["z"])))
        except (TypeError, ValueError):
            continue
    if len(pts) < 4:
        raise SystemExit("contour needs at least 4 x, y, z rows")
    _cap(None, len(pts), 400, "points", opt["unbounded"])
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    nx = ny = 8
    lo_x, hi_x, lo_y, hi_y = min(xs), max(xs), min(ys), max(ys)
    if hi_x == lo_x:
        hi_x += 1
    if hi_y == lo_y:
        hi_y += 1
    acc = [[[] for _ in range(nx)] for _ in range(ny)]
    for x, y, z in pts:
        i = min(nx - 1, int((x - lo_x) / (hi_x - lo_x) * nx))
        j = min(ny - 1, int((y - lo_y) / (hi_y - lo_y) * ny))
        acc[j][i].append(z)
    grid = [[(sum(cell) / len(cell) if cell else None) for cell in row] for row in acc]
    known = [z for row in grid for z in row if z is not None]
    levels = []
    if known and max(known) != min(known):
        levels = [min(known) + (max(known) - min(known)) * (k + 1) / 5 for k in range(4)]
    gx = [lo_x + (hi_x - lo_x) * (i + 0.5) / nx for i in range(nx)]
    gy = [lo_y + (hi_y - lo_y) * (j + 0.5) / ny for j in range(ny)]
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 320)
    X, Y = _axes(parts, t, ox, oy, pw, ph, nice_ticks(lo_x, hi_x), nice_ticks(lo_y, hi_y), opt["grid"])
    segs = _isolines(gx, gy, grid, levels)
    pal = series_palette(t)
    for a, b, level in segs:
        u = 0 if not levels else levels.index(level) / max(len(levels) - 1, 1)
        parts.append(
            f'<line x1="{X(a[0]):.1f}" y1="{Y(a[1]):.1f}" x2="{X(b[0]):.1f}" y2="{Y(b[1]):.1f}" stroke="{_heat_color(t, u)}" stroke-width="1.6"/>')
    if opt["markers"] and len(pts) <= 80:
        for x, y, z in pts:
            _dot(parts, t, X(x), Y(y), 2.4, t["ink"], True, False)
    return _done(parts, opt, W, H, len(pts), f"{len(levels)} levels" if levels else "flat field")


def _json(spec):
    if not isinstance(spec, dict):
        raise SystemExit("this chart reads a JSON spec")
    return spec


def _c_dag(spec, rows, opt):
    spec = _json(spec)
    nodes, edges = spec.get("nodes") or [], spec.get("edges") or []
    opt = dict(opt, spec=spec)
    parts, pos, W, H = _linked(opt, nodes, edges, 12, 24)
    _paint_boxes(parts, opt["t"], pos, _focals(nodes))
    _draw_links(parts, opt["t"], pos, edges)
    return _done(parts, opt, W, H, len(nodes))


def _force_pos(nodes, edges, W, top, height):
    import math
    ids = [n["id"] for n in nodes]
    pos = {}
    for i, n in enumerate(nodes):
        ang = math.tau * i / max(len(nodes), 1)
        pos[n["id"]] = [W / 2 + 150 * math.cos(ang), top + height / 2 + 100 * math.sin(ang)]
    links = [(e.get("from"), e.get("to")) for e in edges if e.get("from") in pos and e.get("to") in pos]
    for _ in range(80):
        force = {i: [0.0, 0.0] for i in ids}
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                ia, ib = ids[a], ids[b]
                dx, dy = pos[ia][0] - pos[ib][0], pos[ia][1] - pos[ib][1]
                dist = math.hypot(dx, dy) or 0.1
                f = 800.0 / (dist * dist)
                force[ia][0] += f * dx / dist
                force[ia][1] += f * dy / dist
                force[ib][0] -= f * dx / dist
                force[ib][1] -= f * dy / dist
        for a, b in links:
            dx, dy = pos[b][0] - pos[a][0], pos[b][1] - pos[a][1]
            dist = math.hypot(dx, dy) or 0.1
            f = (dist - 90) * 0.05
            force[a][0] += max(-12, min(12, f * dx / dist))
            force[a][1] += max(-12, min(12, f * dy / dist))
            force[b][0] -= max(-12, min(12, f * dx / dist))
            force[b][1] -= max(-12, min(12, f * dy / dist))
        for i in ids:
            pos[i][0] = min(W - 46, max(46, pos[i][0] + max(-12, min(12, force[i][0]))))
            pos[i][1] = min(top + height - 16, max(top + 8, pos[i][1] + max(-12, min(12, force[i][1]))))
    return pos


def _c_force(spec, rows, opt, colored=False):
    spec = _json(spec)
    nodes, edges = _with_ids(spec.get("nodes") or []), spec.get("edges") or []
    unbounded = _open_budget(spec, opt["unbounded"])
    _cap(spec, len(nodes), 40, "nodes", unbounded)
    _cap(spec, len(edges), 80, "edges", unbounded)
    if len(nodes) < 1:
        raise SystemExit("need at least one node")
    hh = _hh(opt["title"], opt["sub"])
    W, top, height = 760, hh + 20, 420
    H = top + height + 40
    parts, _ = _fig_open(opt["t"], opt["title"], opt["sub"], W, H)
    t = opt["t"]
    pos = _force_pos(nodes, edges, W, top, height)
    pal = series_palette(t)
    kinds = _ordered(str(n.get("kind") or "") for n in nodes) if colored else []
    kcol = {k: pal[i % len(pal)] for i, k in enumerate(kinds)}
    by = {n["id"]: n for n in nodes}
    for e in edges:
        if e.get("from") in pos and e.get("to") in pos:
            a, b = pos[e["from"]], pos[e["to"]]
            parts.append(
                f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" stroke="{t["muted"]}" stroke-width="1.2"/>')
    for n in nodes:
        x, y = pos[n["id"]]
        focal = n["id"] in _focals(nodes)
        if colored:
            fill = t["accent"] if focal else kcol.get(str(n.get("kind") or ""), t["link"])
        else:
            fill = t["accent"] if focal else t["link"]
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="16" fill="{fill}" stroke="{t["card"]}" stroke-width="1.4"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{y + 28:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(n.get("name") or n["id"], 16))}</text>')
    if colored and len(kinds) > 1:
        _legend(parts, t, [(kcol[k], k or "kind") for k in kinds], 36, H - 34)
    return _done(parts, opt, W, H, len(nodes))


def _c_kg(spec, rows, opt):
    return _c_force(spec, rows, opt, colored=True)


def _c_radial(spec, rows, opt):
    import math
    from collections import defaultdict, deque
    spec = _json(spec)
    nodes, edges = _with_ids(spec.get("nodes") or []), spec.get("edges") or []
    unbounded = _open_budget(spec, opt["unbounded"])
    _cap(spec, len(nodes), 24, "nodes", unbounded)
    if not nodes:
        raise SystemExit("radial needs nodes")
    adj = defaultdict(list)
    deg = defaultdict(int)
    for e in edges:
        if e.get("from") in {n["id"] for n in nodes} and e.get("to") in {n["id"] for n in nodes}:
            adj[e["from"]].append(e["to"])
            adj[e["to"]].append(e["from"])
            deg[e["from"]] += 1
            deg[e["to"]] += 1
    root = spec.get("root") or max(nodes, key=lambda n: deg[n["id"]])["id"]
    ring = {root: 0}
    q = deque([root])
    while q:
        cur = q.popleft()
        for nxt in adj[cur]:
            if nxt not in ring:
                ring[nxt] = ring[cur] + 1
                q.append(nxt)
    extra = max(ring.values(), default=0) + 1
    for n in nodes:
        ring.setdefault(n["id"], extra)
    groups = defaultdict(list)
    for n in nodes:
        groups[ring[n["id"]]].append(n)
    hh = _hh(opt["title"], opt["sub"])
    W, H = 760, hh + 500
    parts, _ = _fig_open(opt["t"], opt["title"], opt["sub"], W, H)
    t = opt["t"]
    cx, cy = W / 2, hh + 250
    pos = {}
    for depth, group in groups.items():
        rad = 0 if depth == 0 else 70 + depth * 78
        for i, n in enumerate(group):
            ang = -math.pi / 2 + math.tau * i / max(len(group), 1)
            pos[n["id"]] = (cx + rad * math.cos(ang), cy + rad * math.sin(ang), n)
    for e in edges:
        if e.get("from") in pos and e.get("to") in pos:
            a, b = pos[e["from"]], pos[e["to"]]
            parts.append(
                f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" stroke="{t["muted"]}" stroke-width="1.2"/>')
    foc = _focals(nodes)
    for nid, (x, y, n) in pos.items():
        col = t["accent"] if nid in foc or nid == root else t["link"]
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="15" fill="{col}"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{y + 28:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(n.get("name") or nid, 14))}</text>')
    return _done(parts, opt, W, H, len(nodes))


def _draw_hierarchy(opt, roots, org=False, edge_labels=False):
    n = sum(1 for _ in _walk_tree(roots))
    cap = 12 if org else 24
    _cap(opt.get("spec"), n, cap, "nodes", opt["unbounded"])
    if not roots:
        raise SystemExit("need a parent tree")
    pos, leaves = _leaf_pos(roots)
    pitch = 180 if org else 120
    gap = 100 if org else 84
    depth = _depth(roots)
    bw, bh = (156, 52) if org else (108, 36)
    margin = bw / 2 + 28
    span = (leaves - 1) * pitch
    W = max(760, int(span + margin * 2))
    top = _hh(opt["title"], opt["sub"]) + 36
    H = int(top + (depth - 1) * gap + bh + 70)
    parts, _ = _fig_open(opt["t"], opt["title"], opt["sub"], W, H)
    t = opt["t"]
    origin = margin + max(0.0, (W - (span + margin * 2)) / 2)

    def at(node):
        x = origin + pos[id(node)][0] * pitch
        y = top + pos[id(node)][1] * gap
        return x, y

    def walk(node):
        x, y = at(node)
        for child in node["children"]:
            cx, cy = at(child)
            mid = y + bh + (cy - (y + bh)) / 2
            parts.append(
                f'<path d="M {x:.1f} {y + bh:.1f} V {mid:.1f} H {cx:.1f} V {cy:.1f}" fill="none" stroke="{t["muted"]}" stroke-width="1.3"/>')
            label = (child.get("raw") or {}).get("label") or ""
            if edge_labels and label:
                parts.append(
                    f'<text x="{(x + cx) / 2:.1f}" y="{mid - 4:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="middle">{esc(_short(label, 16))}</text>')
            walk(child)
        sub = (node.get("raw") or {}).get("sub") or ""
        hit = _hit(opt["highlights"], node["name"])
        fill = t["accent_tint"] if hit else t["card"]
        stroke = t["accent"] if hit else t["ink"]
        parts.append(
            f'<rect x="{x - bw / 2:.1f}" y="{y:.1f}" width="{bw}" height="{bh}" rx="2" fill="{fill}" stroke="{stroke}"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{y + (22 if sub else bh / 2 + 4):.1f}" font-size="13" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(node["name"], 18))}</text>')
        if sub:
            parts.append(
                f'<text x="{x:.1f}" y="{y + 38:.1f}" font-size="11" font-family="{FONT}" fill="{t["muted"]}" text-anchor="middle">{esc(_short(sub, 22))}</text>')

    for root in roots:
        walk(root)
    return _done(parts, opt, W, H, n)


def _c_tree(spec, rows, opt):
    spec = _json(spec)
    opt = dict(opt, spec=spec)
    return _draw_hierarchy(opt, _tree_from(spec.get("nodes") or []))


def _c_dtree(spec, rows, opt):
    spec = _json(spec)
    opt = dict(opt, spec=spec)
    return _draw_hierarchy(opt, _tree_from(spec.get("nodes") or []), edge_labels=True)


def _c_org(spec, rows, opt):
    spec = _json(spec)
    opt = dict(opt, spec=spec)
    return _draw_hierarchy(opt, _tree_from(spec.get("nodes") or []), org=True)


def _c_nested(spec, rows, opt):
    spec = _json(spec)
    roots = _tree_from(spec.get("nodes") or [])
    n = sum(1 for _ in _walk_tree(roots))
    _cap(spec, n, 20, "nodes", _open_budget(spec, opt["unbounded"]))
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 400, ox=28, right=28)
    pal = series_palette(t)

    def draw(node, x, y, w, h, depth, idx):
        if depth > 4 or w < 8 or h < 8:
            return
        col = pal[idx % len(pal)]
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{t["card"]}" stroke="{col}" stroke-width="1.4"/>')
        if w > 36 and h > 16:
            parts.append(
                f'<text x="{x + 8:.1f}" y="{y + 16:.1f}" font-size="12" font-family="{FONT}" fill="{t["ink"]}">{esc(_short(node["name"], int(max(w / 8, 4))))}</text>')
        kids = node["children"]
        if not kids or depth == 4:
            return
        rects = _partition([(c, c["val"]) for c in kids], x + 6, y + 24, max(4, w - 12), max(4, h - 30), True)
        for i, (child, cx, cy, cw, ch) in enumerate(rects):
            draw(child, cx, cy, cw, ch, depth + 1, idx + i + 1)

    rects = _partition([(r, r["val"]) for r in roots], ox, oy, pw, ph, True)
    for i, (node, x, y, w, h) in enumerate(rects):
        draw(node, x, y, w, h, 1, i)
    return _done(parts, opt, W, H, n)


def _c_context(spec, rows, opt):
    spec = _json(spec)
    nodes, edges = _with_ids(spec.get("nodes") or []), spec.get("edges") or []
    _cap(spec, len(nodes), 9, "nodes", _open_budget(spec, opt["unbounded"]))
    people = [n for n in nodes if str(n.get("kind") or "") == "person"]
    systems = [n for n in nodes if n not in people]
    if not systems:
        systems, people = people, []
    hh = _hh(opt["title"], opt["sub"])
    W, H = 760, max(420, hh + 80 + max(len(people), len(systems), 1) * 80)
    parts, _ = _fig_open(opt["t"], opt["title"], opt["sub"], W, H)
    parts.append(markers(opt["t"]))
    t = opt["t"]
    pos = {}
    for i, n in enumerate(people):
        pos[n["id"]] = (150, hh + 70 + i * 78, n)
    for i, n in enumerate(systems):
        pos[n["id"]] = (480, hh + 70 + i * 84, n)
    foc = _focals(nodes)
    for e in edges:
        if e.get("from") not in pos or e.get("to") not in pos:
            continue
        x1, y1, _ = pos[e["from"]]
        x2, y2, _ = pos[e["to"]]
        parts.append(
            f'<line x1="{x1 + 28:.1f}" y1="{y1:.1f}" x2="{x2 - 80:.1f}" y2="{y2:.1f}" stroke="{t["muted"]}" stroke-width="1.4" marker-end="url(#a)"/>')
        if e.get("label"):
            parts.append(arrow_label(t, (x1 + x2) / 2, (y1 + y2) / 2, str(e["label"]).upper()))
    for n in people:
        x, y, _ = pos[n["id"]]
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="26" fill="{t["card"]}" stroke="{t["ink"]}" stroke-width="1.3"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{y + 4:.1f}" font-size="12" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(n["name"], 10))}</text>')
    for n in systems:
        x, y, _ = pos[n["id"]]
        focal = n["id"] in foc
        _paint_one = focal
        sw = "1.6" if focal else "1.2"
        fill = t["accent_tint"] if focal else t["card"]
        stroke = t["accent"] if focal else t["ink"]
        parts.append(
            f'<rect x="{x - 80:.1f}" y="{y - 28:.1f}" width="160" height="56" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{y + 4:.1f}" font-size="13" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(n["name"], 18))}</text>')
    return _done(parts, opt, W, H, len(nodes))


def _c_uml(spec, rows, opt):
    spec = _json(spec)
    nodes, edges = _with_ids(spec.get("nodes") or []), spec.get("edges") or []
    _cap(spec, len(nodes), 7, "classes", _open_budget(spec, opt["unbounded"]))
    rev = [{"from": e.get("to"), "to": e.get("from")} for e in edges]
    rank = _layers_of(nodes, rev)
    from collections import defaultdict
    rows_l = defaultdict(list)
    for n in nodes:
        rows_l[rank.get(n["id"], 0)].append(n)
    hh = _hh(opt["title"], opt["sub"])
    widest = max((len(v) for v in rows_l.values()), default=1)
    W = max(760, 240 * (widest + 1))
    def box_h(n):
        return 36 + 14 * min(6, len(n.get("attrs") or [])) + 14 * min(6, len(n.get("methods") or [])) + 12
    y = hh + 30
    pos = {}
    for key in sorted(rows_l):
        row = rows_l[key]
        h = max(box_h(n) for n in row)
        for j, n in enumerate(row):
            x = W * (j + 1) / (len(row) + 1)
            pos[n["id"]] = (x, y, h, n)
        y += h + 48
    H = int(y + 40)
    parts, _ = _fig_open(opt["t"], opt["title"], opt["sub"], W, H)
    parts.append(markers(opt["t"]))
    t = opt["t"]
    for e in edges:
        if e.get("from") not in pos or e.get("to") not in pos:
            continue
        x1, y1, h1, _ = pos[e["from"]]
        x2, y2, h2, _ = pos[e["to"]]
        inherit = str(e.get("kind") or "") == "inherit"
        head = "none" if inherit else "url(#a)"
        parts.append(
            f'<path d="M {x1:.1f} {y1:.1f} V {(y1 + y2) / 2:.1f} H {x2:.1f} V {y2 + h2:.1f}" fill="none" stroke="{t["muted"]}" stroke-width="1.3" marker-end="{head}"/>')
        if inherit:
            parts.append(
                f'<polygon points="{x2:.1f},{y2 + h2:.1f} {x2 - 7:.1f},{y2 + h2 + 12:.1f} {x2 + 7:.1f},{y2 + h2 + 12:.1f}" fill="{t["paper"]}" stroke="{t["ink"]}"/>')
    for nid, (x, y0, h, n) in pos.items():
        w = 180
        parts.append(f'<rect x="{x - w / 2:.1f}" y="{y0:.1f}" width="{w}" height="{h}" fill="{t["card"]}" stroke="{t["ink"]}"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{y0 + 18:.1f}" font-size="13" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(n.get("name") or nid, 20))}</text>')
        parts.append(f'<line x1="{x - w / 2:.1f}" y1="{y0 + 28:.1f}" x2="{x + w / 2:.1f}" y2="{y0 + 28:.1f}" stroke="{t["rule"]}"/>')
        yy = y0 + 44
        for attr in (n.get("attrs") or [])[:6]:
            parts.append(
                f'<text x="{x - w / 2 + 8:.1f}" y="{yy:.1f}" font-size="11" font-family="{FONT}" fill="{t["muted"]}">{esc(_short(attr, 22))}</text>')
            yy += 14
        parts.append(f'<line x1="{x - w / 2:.1f}" y1="{yy - 6:.1f}" x2="{x + w / 2:.1f}" y2="{yy - 6:.1f}" stroke="{t["rule"]}"/>')
        for method in (n.get("methods") or [])[:6]:
            parts.append(
                f'<text x="{x - w / 2 + 8:.1f}" y="{yy + 8:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}">{esc(_short(method, 22))}</text>')
            yy += 14
    return _done(parts, opt, W, H, len(nodes))


def _c_deploy(spec, rows, opt):
    spec = _json(spec)
    zones = spec.get("zones") or []
    _cap(spec, len(zones), 3, "zones", _open_budget(spec, opt["unbounded"]))
    if not zones:
        raise SystemExit("deploy needs zones")
    tall = max(len(z.get("nodes") or []) for z in zones)
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, max(220, 70 + tall * 64), ox=28, right=28, bottom=40)
    zw = pw / len(zones)
    for i, zone in enumerate(zones):
        x = ox + i * zw
        parts.append(
            f'<rect x="{x + 6:.1f}" y="{oy:.1f}" width="{zw - 12:.1f}" height="{ph:.1f}" rx="4" fill="{t["card"]}" stroke="{t["rule"]}"/>')
        parts.append(
            f'<text x="{x + 16:.1f}" y="{oy + 20:.1f}" font-size="13" font-family="{FONT}" fill="{t["ink"]}">{esc(_short(zone.get("name") or zone.get("id") or "zone", 18))}</text>')
        for j, node in enumerate((zone.get("nodes") or [])[:8]):
            parts.append(
                f'<rect x="{x + 18:.1f}" y="{oy + 36 + j * 58:.1f}" width="{zw - 40:.1f}" height="46" rx="2" fill="{t["paper"]}" stroke="{t["ink"]}"/>')
            parts.append(
                f'<text x="{x + zw / 2:.1f}" y="{oy + 64 + j * 58:.1f}" font-size="12" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(node.get("name") or node.get("id"), 16))}</text>')
    return _done(parts, opt, W, H, len(zones))


def _c_layers(spec, rows, opt):
    spec = _json(spec)
    layers = spec.get("layers") or []
    _cap(spec, len(layers), 8, "layers", _open_budget(spec, opt["unbounded"]))
    if not layers:
        raise SystemExit("layers needs a layers list")
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, max(200, len(layers) * 58), ox=28, right=28, bottom=36)
    band = ph / len(layers)
    for i, layer in enumerate(layers):
        y = oy + i * band
        parts.append(
            f'<rect x="{ox:.1f}" y="{y + 4:.1f}" width="{pw:.1f}" height="{band - 8:.1f}" fill="{t["card"]}" stroke="{t["ink"]}"/>')
        parts.append(
            f'<text x="{ox + 16:.1f}" y="{y + band / 2 + 4:.1f}" font-size="14" font-family="{FONT}" fill="{t["ink"]}">{esc(_short(layer.get("name") or "", 24))}</text>')
        if layer.get("sub"):
            parts.append(
                f'<text x="{ox + pw - 16:.1f}" y="{y + band / 2 + 4:.1f}" font-size="12" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">{esc(_short(layer["sub"], 28))}</text>')
    return _done(parts, opt, W, H, len(layers))


def _c_integration(spec, rows, opt):
    spec = _json(spec)
    nodes, edges = _with_ids(spec.get("nodes") or []), spec.get("edges") or []
    _cap(spec, len(nodes), 9, "nodes", _open_budget(spec, opt["unbounded"]))
    cols = {"source": [], "core": [], "consumer": []}
    for n in nodes:
        key = str(n.get("col") or "core")
        cols[key if key in cols else "core"].append(n)
    hh = _hh(opt["title"], opt["sub"])
    tall = max(len(v) for v in cols.values())
    W, H = 820, int(hh + 80 + max(tall, 1) * 90)
    parts, _ = _fig_open(opt["t"], opt["title"], opt["sub"], W, H)
    parts.append(markers(opt["t"]))
    t = opt["t"]
    xs = {"source": 170, "core": 410, "consumer": 650}
    pos = {}
    for key, group in cols.items():
        for i, n in enumerate(group):
            pos[n["id"]] = (xs[key], hh + 70 + i * 90, n)
    _paint_boxes(parts, t, pos, _focals(nodes))
    _draw_links(parts, t, pos, edges)
    for key, x in xs.items():
        parts.append(
            f'<text x="{x:.1f}" y="{hh + 28:.1f}" font-size="11" font-family="{FONT}" fill="{t["muted"]}" text-anchor="middle">{key}</text>')
    return _done(parts, opt, W, H, len(nodes))


def _c_current(spec, rows, opt):
    spec = _json(spec)
    nodes = _with_ids(spec.get("nodes") or [])
    _cap(spec, len(nodes), 18, "nodes", _open_budget(spec, opt["unbounded"]))
    groups = _ordered(str(n.get("group") or "Other") for n in nodes)
    hh = _hh(opt["title"], opt["sub"])
    tall = max(sum(1 for n in nodes if str(n.get("group") or "Other") == g) for g in groups) if groups else 1
    W = max(760, 200 * max(len(groups), 1) + 40)
    H = int(hh + 70 + tall * 70)
    parts, _ = _fig_open(opt["t"], opt["title"], opt["sub"], W, H)
    t = opt["t"]
    for i, g in enumerate(groups):
        x = 30 + i * (W - 50) / max(len(groups), 1)
        colw = (W - 50) / max(len(groups), 1)
        parts.append(
            f'<text x="{x + 12:.1f}" y="{hh + 28:.1f}" font-size="12" font-family="{FONT}" fill="{t["muted"]}">{esc(_short(g, 18))}</text>')
        j = 0
        for n in nodes:
            if str(n.get("group") or "Other") != g:
                continue
            parts.append(
                f'<rect x="{x + 8:.1f}" y="{hh + 42 + j * 64:.1f}" width="{colw - 24:.1f}" height="50" rx="2" fill="{t["card"]}" stroke="{t["ink"]}"/>')
            parts.append(
                f'<text x="{x + colw / 2:.1f}" y="{hh + 72 + j * 64:.1f}" font-size="13" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(n["name"], 16))}</text>')
            j += 1
    return _done(parts, opt, W, H, len(nodes))


def _many_card(card):
    return str(card or "1").strip().lower() in ("*", "n", "m", "many", "*") or str(card or "").endswith("*") or str(card or "").endswith("n")


def _crow(parts, t, x1, y1, x2, y2, many):
    import math
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    ex, ey = x2 - ux * 8, y2 - uy * 8
    sx, sy = ex - ux * 16, ey - uy * 16
    parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{sx:.1f}" y2="{sy:.1f}" stroke="{t["muted"]}" stroke-width="1.3"/>')
    if many:
        for s in (-1, 0, 1):
            parts.append(
                f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex + px * s * 7:.1f}" y2="{ey + py * s * 7:.1f}" stroke="{t["ink"]}" stroke-width="1.2"/>')
    else:
        parts.append(
            f'<line x1="{ex - px * 7:.1f}" y1="{ey - py * 7:.1f}" x2="{ex + px * 7:.1f}" y2="{ey + py * 7:.1f}" stroke="{t["ink"]}" stroke-width="1.4"/>')


def _c_er(spec, rows, opt):
    spec = _json(spec)
    ents = spec.get("entities") or []
    rels = spec.get("relations") or []
    _cap(spec, len(ents), 8, "entities", _open_budget(spec, opt["unbounded"]))
    if not ents:
        raise SystemExit("er needs entities")
    cols = 2 if len(ents) > 3 else len(ents)
    rows_n = (len(ents) + cols - 1) // cols
    hh = _hh(opt["title"], opt["sub"])
    W = max(760, cols * 340)
    box_h = 120
    H = int(hh + 40 + rows_n * (box_h + 36))
    parts, _ = _fig_open(opt["t"], opt["title"], opt["sub"], W, H)
    t = opt["t"]
    pos = {}
    for i, ent in enumerate(ents):
        c, r = i % cols, i // cols
        x = W * (c + 1) / (cols + 1)
        y = hh + 36 + r * (box_h + 36)
        pos[ent.get("id") or ent.get("name")] = (x, y, ent)
    for rel in rels:
        if rel.get("from") not in pos or rel.get("to") not in pos:
            continue
        x1, y1, _ = pos[rel["from"]]
        x2, y2, _ = pos[rel["to"]]
        _crow(parts, t, x1 + 90, y1 + 28, x2 - 90, y2 + 28, _many_card(rel.get("to_card")))
        _crow(parts, t, x2 - 90, y2 + 40, x1 + 90, y1 + 40, _many_card(rel.get("from_card")))
    for eid, (x, y, ent) in pos.items():
        attrs = ent.get("attrs") or []
        h = 36 + 16 * min(6, len(attrs))
        parts.append(f'<rect x="{x - 90:.1f}" y="{y:.1f}" width="180" height="{h}" fill="{t["card"]}" stroke="{t["ink"]}"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{y + 18:.1f}" font-size="13" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(ent.get("name") or eid, 18))}</text>')
        for i, attr in enumerate(attrs[:6]):
            mark = "pk" if str(attr.get("key") or "").lower() == "pk" else ""
            parts.append(
                f'<text x="{x - 80:.1f}" y="{y + 38 + i * 16:.1f}" font-size="11" font-family="{FONT}" fill="{t["muted"]}">{esc(_short(attr.get("name") or "", 16))}</text>')
            if mark:
                parts.append(
                    f'<text x="{x + 70:.1f}" y="{y + 38 + i * 16:.1f}" font-size="10" font-family="{FONT}" fill="{t["accent"]}" text-anchor="end">pk</text>')
    return _done(parts, opt, W, H, len(ents))


def _c_wardley(spec, rows, opt):
    spec = _json(spec)
    nodes, edges = _with_ids(spec.get("nodes") or []), spec.get("edges") or []
    _cap(spec, len(nodes), 12, "components", _open_budget(spec, opt["unbounded"]))
    if not nodes:
        raise SystemExit("wardley needs nodes with visibility and evolution")
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 360, ox=70, bottom=64)
    parts.append(f'<rect x="{ox}" y="{oy}" width="{pw}" height="{ph}" fill="{t["card"]}" stroke="{t["rule"]}"/>')
    for frac, lab in ((0.25, "Custom"), (0.5, "Product"), (0.75, "")):
        x = ox + frac * pw
        parts.append(f'<line x1="{x:.1f}" y1="{oy}" x2="{x:.1f}" y2="{oy + ph}" stroke="{t["rule"]}"/>')
    for frac, lab in ((0.125, "Genesis"), (0.375, "Custom"), (0.625, "Product"), (0.875, "Commodity")):
        parts.append(
            f'<text x="{ox + frac * pw:.1f}" y="{oy + ph + 18:.1f}" font-size="11" font-family="{FONT}" fill="{t["muted"]}" text-anchor="middle">{lab}</text>')
    parts.append(
        f'<text x="{ox - 8}" y="{oy + 12:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">visible</text>')

    def px(n):
        evo = min(1.0, max(0.0, float(n.get("evolution") or 0)))
        vis = min(1.0, max(0.0, float(n.get("visibility") or 0)))
        return ox + evo * pw, oy + (1 - vis) * ph

    by = {n["id"]: n for n in nodes}
    for e in edges:
        if e.get("from") in by and e.get("to") in by:
            x1, y1 = px(by[e["from"]])
            x2, y2 = px(by[e["to"]])
            parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{t["muted"]}" stroke-width="1.2"/>')
    for n in nodes:
        x, y = px(n)
        hit = _hit(opt["highlights"], n["name"]) or n.get("focal")
        parts.append(
            f'<rect x="{x - 46:.1f}" y="{y - 14:.1f}" width="92" height="28" rx="2" fill="{t["accent_tint"] if hit else t["paper"]}" stroke="{t["accent"] if hit else t["ink"]}"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{y + 4:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(n["name"], 14))}</text>')
    return _done(parts, opt, W, H, len(nodes))


def _c_swim(spec, rows, opt):
    spec = _json(spec)
    lanes = spec.get("lanes") or []
    nodes = _with_ids(spec.get("nodes") or [])
    edges = spec.get("edges") or []
    _cap(spec, len(nodes), 12, "nodes", _open_budget(spec, opt["unbounded"]))
    if not lanes:
        raise SystemExit("swim needs lanes")
    hh = _hh(opt["title"], opt["sub"])
    lane_h = 110
    W, H = 860, int(hh + 36 + len(lanes) * lane_h + 40)
    parts, _ = _fig_open(opt["t"], opt["title"], opt["sub"], W, H)
    parts.append(markers(opt["t"]))
    t = opt["t"]
    lane_y = {}
    for i, lane in enumerate(lanes):
        y = hh + 24 + i * lane_h
        lane_y[lane.get("id")] = y
        parts.append(f'<rect x="120" y="{y:.1f}" width="700" height="{lane_h - 8}" fill="{t["card"]}" stroke="{t["rule"]}"/>')
        parts.append(
            f'<text x="16" y="{y + lane_h / 2:.1f}" font-size="12" font-family="{FONT}" fill="{t["ink"]}">{esc(_short(lane.get("name") or "", 12))}</text>')
    buckets = {}
    for n in nodes:
        buckets.setdefault(n.get("lane"), []).append(n)
    pos = {}
    for lane_id, group in buckets.items():
        y = lane_y.get(lane_id, hh + 24) + lane_h / 2
        for i, n in enumerate(group):
            x = 200 + i * 180
            pos[n["id"]] = (x, y, n)
    _paint_boxes(parts, t, pos, _focals(nodes), w=140, h=48)
    _draw_links(parts, t, pos, edges)
    return _done(parts, opt, W, H, len(nodes))


def _c_state(spec, rows, opt):
    import math
    spec = _json(spec)
    nodes, edges = _with_ids(spec.get("nodes") or []), spec.get("edges") or []
    _cap(spec, len(nodes), 8, "states", _open_budget(spec, opt["unbounded"]))
    if not nodes:
        raise SystemExit("state needs nodes")
    hh = _hh(opt["title"], opt["sub"])
    W = max(760, 140 + len(nodes) * 140)
    H = hh + 280
    parts, _ = _fig_open(opt["t"], opt["title"], opt["sub"], W, H)
    parts.append(markers(opt["t"]))
    t = opt["t"]
    idx = {n["id"]: i for i, n in enumerate(nodes)}
    pos = {n["id"]: (120 + i * (W - 180) / max(len(nodes) - 1, 1), hh + 150) for i, n in enumerate(nodes)}
    for e in edges:
        if e.get("from") not in pos or e.get("to") not in pos:
            continue
        x1, y1 = pos[e["from"]]
        x2, y2 = pos[e["to"]]
        back = idx[e["to"]] <= idx[e["from"]]
        if back:
            mx, my = (x1 + x2) / 2, y1 - 70
            parts.append(
                f'<path d="M {x1:.1f} {y1 - 22:.1f} Q {mx:.1f} {my:.1f} {x2:.1f} {y2 - 22:.1f}" fill="none" stroke="{t["muted"]}" stroke-width="1.4" marker-end="url(#a)"/>')
            lx, ly = mx, my
        else:
            parts.append(
                f'<line x1="{x1 + 24:.1f}" y1="{y1:.1f}" x2="{x2 - 28:.1f}" y2="{y2:.1f}" stroke="{t["muted"]}" stroke-width="1.4" marker-end="url(#a)"/>')
            lx, ly = (x1 + x2) / 2, y1 - 10
        if e.get("label"):
            parts.append(
                f'<text x="{lx:.1f}" y="{ly - 6:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(e["label"], 16))}</text>')
    for n in nodes:
        x, y = pos[n["id"]]
        hit = n["id"] in _focals(nodes)
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="26" fill="{t["accent_tint"] if hit else t["card"]}" stroke="{t["accent"] if hit else t["ink"]}" stroke-width="1.4"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{y + 46:.1f}" font-size="12" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(n["name"], 16))}</text>')
    return _done(parts, opt, W, H, len(nodes))


def _c_bpmn(spec, rows, opt):
    spec = _json(spec)
    nodes, edges = _with_ids(spec.get("nodes") or []), spec.get("edges") or []
    _cap(spec, len(nodes), 12, "nodes", _open_budget(spec, opt["unbounded"]))
    if not nodes:
        raise SystemExit("bpmn needs nodes")
    rank = _layers_of(nodes, edges)
    from collections import defaultdict
    layers = defaultdict(list)
    for n in nodes:
        layers[rank.get(n["id"], 0)].append(n)
    hh = _hh(opt["title"], opt["sub"])
    widest = max(len(v) for v in layers.values())
    W = max(760, 200 * (widest + 1))
    gap = 120
    H = int(hh + 50 + max(rank.values()) * gap + 100)
    parts, _ = _fig_open(opt["t"], opt["title"], opt["sub"], W, H)
    parts.append(markers(opt["t"]))
    t = opt["t"]
    pos = {}
    for key in sorted(layers):
        row = layers[key]
        for j, n in enumerate(row):
            pos[n["id"]] = (W * (j + 1) / (len(row) + 1), hh + 60 + key * gap, n)
    for e in edges:
        if e.get("from") not in pos or e.get("to") not in pos:
            continue
        x1, y1, _ = pos[e["from"]]
        x2, y2, _ = pos[e["to"]]
        if abs(y1 - y2) < 8:
            parts.append(
                f'<line x1="{x1 + 36:.1f}" y1="{y1:.1f}" x2="{x2 - 40:.1f}" y2="{y2:.1f}" stroke="{t["muted"]}" stroke-width="1.4" marker-end="url(#a)"/>')
            lx, ly = (x1 + x2) / 2, y1
        else:
            mid = (y1 + y2) / 2
            parts.append(
                f'<path d="M {x1:.1f} {y1 + 28:.1f} V {mid:.1f} H {x2:.1f} V {y2 - 32:.1f}" fill="none" stroke="{t["muted"]}" stroke-width="1.4" marker-end="url(#a)"/>')
            lx, ly = (x1 + x2) / 2, mid
        if e.get("label"):
            parts.append(
                f'<text x="{lx:.1f}" y="{ly - 6:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(e["label"], 14))}</text>')
    for n in nodes:
        x, y, _ = pos[n["id"]]
        shape = str(n.get("shape") or "task")
        if shape == "event":
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="22" fill="{t["card"]}" stroke="{t["ink"]}" stroke-width="1.3"/>')
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="17" fill="none" stroke="{t["ink"]}" stroke-width="1"/>')
        elif shape == "gateway":
            parts.append(
                f'<polygon points="{x:.1f},{y - 24:.1f} {x + 28:.1f},{y:.1f} {x:.1f},{y + 24:.1f} {x - 28:.1f},{y:.1f}" fill="{t["card"]}" stroke="{t["ink"]}"/>')
        else:
            parts.append(
                f'<rect x="{x - 54:.1f}" y="{y - 22:.1f}" width="108" height="44" rx="8" fill="{t["card"]}" stroke="{t["ink"]}"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{y + 4:.1f}" font-size="12" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(n["name"], 12))}</text>')
    return _done(parts, opt, W, H, len(nodes))


def _c_fishbone(spec, rows, opt):
    spec = _json(spec)
    ribs = spec.get("ribs") or []
    _cap(spec, len(ribs), 6, "ribs", _open_budget(spec, opt["unbounded"]))
    if not ribs:
        raise SystemExit("fishbone needs ribs")
    problem = spec.get("problem") or opt["title"] or "Problem"
    W, H = 860, 460
    parts, _ = _fig_open(opt["t"], opt["title"], opt["sub"], W, H)
    t = opt["t"]
    y = 250
    parts.append(f'<line x1="70" y1="{y}" x2="690" y2="{y}" stroke="{t["ink"]}" stroke-width="1.6"/>')
    parts.append(f'<rect x="690" y="{y - 22}" width="140" height="44" rx="2" fill="{t["accent_tint"]}" stroke="{t["accent"]}"/>')
    parts.append(
        f'<text x="760" y="{y + 4}" font-size="13" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(problem, 16))}</text>')
    for i, rib in enumerate(ribs[:6]):
        x = 120 + i * 90
        up = i % 2 == 0
        x2, y2 = x + 80, 120 if up else 380
        parts.append(f'<line x1="{x}" y1="{y}" x2="{x2}" y2="{y2}" stroke="{t["muted"]}" stroke-width="1.3"/>')
        parts.append(
            f'<text x="{x2 + 4}" y="{y2 + (-6 if up else 12)}" font-size="12" font-family="{FONT}" fill="{t["ink"]}">{esc(_short(rib.get("name") or "", 14))}</text>')
        causes = rib.get("causes") or []
        for j, cause in enumerate(causes[:4]):
            u = (j + 1) / (min(len(causes), 4) + 1)
            cx, cy = x + (x2 - x) * u, y + (y2 - y) * u
            tick = 42
            parts.append(
                f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{cx + tick:.1f}" y2="{cy:.1f}" stroke="{t["muted"]}" stroke-width="1.1"/>')
            parts.append(
                f'<text x="{cx + tick + 6:.1f}" y="{cy + 4:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}">{esc(_short(cause, 16))}</text>')
    return _done(parts, opt, W, H, len(ribs))


def _c_flywheel(spec, rows, opt):
    import math
    spec = _json(spec)
    nodes = spec.get("nodes") or []
    _cap(spec, len(nodes), 8, "steps", _open_budget(spec, opt["unbounded"]))
    if len(nodes) < 2:
        raise SystemExit("flywheel needs at least two nodes")
    hh = _hh(opt["title"], opt["sub"])
    W, H = 760, hh + 460
    parts, _ = _fig_open(opt["t"], opt["title"], opt["sub"], W, H)
    parts.append(markers(opt["t"]))
    t = opt["t"]
    cx, cy, rad = W / 2, hh + 230, 150
    pts = []
    for i, n in enumerate(nodes):
        ang = -math.pi / 2 + math.tau * i / len(nodes)
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang), ang, n))
    for i, (x, y, ang, n) in enumerate(pts):
        x2, y2, ang2, _ = pts[(i + 1) % len(pts)]
        parts.append(
            f'<path d="M {x:.1f} {y:.1f} A {rad:.1f} {rad:.1f} 0 0 1 {x2:.1f} {y2:.1f}" fill="none" stroke="{t["link"]}" stroke-width="1.6" marker-end="url(#a)"/>')
    for x, y, ang, n in pts:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="28" fill="{t["card"]}" stroke="{t["ink"]}"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{y + 4:.1f}" font-size="12" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(n.get("name") or "", 10))}</text>')
    hub = spec.get("hub") or ""
    if hub:
        parts.append(
            f'<text x="{cx:.1f}" y="{cy + 4:.1f}" font-size="16" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(hub, 16))}</text>')
    return _done(parts, opt, W, H, len(nodes))


def _c_kanban(spec, rows, opt):
    spec = _json(spec)
    cols = spec.get("columns") or []
    if not cols:
        raise SystemExit("kanban needs columns")
    _cap(spec, len(cols), 6, "columns", _open_budget(spec, opt["unbounded"]))
    tall = max(len(c.get("cards") or []) for c in cols)
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, max(220, 40 + tall * 58), ox=24, right=24, bottom=36)
    cw = pw / len(cols)
    for i, col in enumerate(cols):
        x = ox + i * cw
        parts.append(
            f'<text x="{x + 12:.1f}" y="{oy + 16:.1f}" font-size="13" font-family="{FONT}" fill="{t["ink"]}">{esc(_short(col.get("name") or "", 16))}</text>')
        for j, card in enumerate(col.get("cards") or []):
            blocked = bool(card.get("blocked"))
            stroke = t["accent"] if blocked else t["ink"]
            sw = "1.6" if blocked else "1.1"
            parts.append(
                f'<rect x="{x + 8:.1f}" y="{oy + 28 + j * 56:.1f}" width="{cw - 20:.1f}" height="46" rx="2" fill="{t["card"]}" stroke="{stroke}" stroke-width="{sw}"/>')
            parts.append(
                f'<text x="{x + cw / 2:.1f}" y="{oy + 56 + j * 56:.1f}" font-size="12" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(card.get("name") or "", 18))}</text>')
    return _done(parts, opt, W, H, len(cols))


def _c_gantt(spec, rows, opt):
    spec = _json(spec)
    tasks = spec.get("tasks") or []
    if not tasks:
        raise SystemExit("gantt needs tasks")
    _cap(spec, len(tasks), 16, "tasks", _open_budget(spec, opt["unbounded"]))
    parsed = []
    dated = False
    for task in tasks:
        a, d1 = _when(task.get("start"))
        b, d2 = _when(task.get("end"))
        dated = dated or d1 or d2
        parsed.append((str(task.get("name") or ""), a, b))
    lo, hi = min(a for _, a, _ in parsed), max(b for _, _, b in parsed)
    if lo == hi:
        hi = lo + 1
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, max(200, len(parsed) * 32), ox=140)
    xt = nice_ticks(lo, hi)
    span = (xt[-1] - xt[0]) or 1

    def X(v):
        return ox + (v - xt[0]) / span * pw

    parts.append(f'<line x1="{ox}" y1="{oy + ph}" x2="{ox + pw}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1"/>')
    import datetime
    for v in xt:
        x = X(v)
        if opt["grid"]:
            parts.append(f'<line x1="{x:.1f}" y1="{oy}" x2="{x:.1f}" y2="{oy + ph}" stroke="{t["rule"]}"/>')
        label = datetime.date.fromordinal(int(v)).isoformat() if dated else fmt_tick(v)
        parts.append(
            f'<text x="{x:.1f}" y="{oy + ph + 16}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="middle">{esc(label)}</text>')
    for i, (name, a, b) in enumerate(parsed):
        y = oy + (i + 0.5) * ph / len(parsed)
        hit = _hit(opt["highlights"], name)
        parts.append(
            f'<rect x="{X(min(a, b)):.1f}" y="{y - 8:.1f}" width="{max(2, abs(X(b) - X(a))):.1f}" height="16" rx="2" fill="{t["accent"] if hit else t["link"]}"/>')
        parts.append(
            f'<text x="{ox - 8}" y="{y + 3:.1f}" font-size="11" font-family="{FONT}" fill="{t["ink"]}" text-anchor="end">{esc(_short(name, 18))}</text>')
    return _done(parts, opt, W, H, len(parsed))


def _c_timeline(spec, rows, opt):
    spec = _json(spec)
    events = spec.get("events") or []
    if not events:
        raise SystemExit("timeline needs events")
    _cap(spec, len(events), 12, "events", _open_budget(spec, opt["unbounded"]))
    parsed = []
    for ev in events:
        d = _parse_date(ev.get("at"))
        parsed.append((str(ev.get("name") or ""), d, str(ev.get("at") or "")))
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 220, ox=50, right=40)
    y = oy + ph / 2
    parts.append(f'<line x1="{ox}" y1="{y:.1f}" x2="{ox + pw}" y2="{y:.1f}" stroke="{t["ink"]}" stroke-width="1.3"/>')
    n = len(parsed)
    for i, (name, d, raw) in enumerate(parsed):
        x = ox + (i + 0.5) * pw / n
        up = i % 2 == 0
        y2 = y - 36 if up else y + 36
        parts.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{y2:.1f}" stroke="{t["muted"]}"/>')
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{t["link"]}"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{y2 + (-8 if up else 16):.1f}" font-size="12" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(name, 16))}</text>')
        parts.append(
            f'<text x="{x:.1f}" y="{y + (18 if up else -10):.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="middle">{esc(_short(raw, 12))}</text>')
    return _done(parts, opt, W, H, n)


def _c_journey(spec, rows, opt):
    spec = _json(spec)
    stages = spec.get("stages") or []
    if not stages:
        raise SystemExit("journey needs stages")
    _cap(spec, len(stages), 8, "stages", _open_budget(spec, opt["unbounded"]))
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 260, ox=50, right=40, bottom=64)
    scores = [max(0, min(5, float(s.get("score") or 0))) for s in stages]

    def Y(v):
        return oy + ph - v / 5 * ph

    parts.append(f'<line x1="{ox}" y1="{oy + ph}" x2="{ox + pw}" y2="{oy + ph}" stroke="{t["ink"]}"/>')
    for v in range(6):
        y = Y(v)
        if opt["grid"]:
            parts.append(f'<line x1="{ox}" y1="{y:.1f}" x2="{ox + pw}" y2="{y:.1f}" stroke="{t["rule"]}"/>')
        parts.append(
            f'<text x="{ox - 8}" y="{y + 3:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">{v}</text>')
    xs = [ox + (i + 0.5) * pw / len(stages) for i in range(len(stages))]
    d = " ".join(f'{"M" if i == 0 else "L"} {xs[i]:.1f} {Y(scores[i]):.1f}' for i in range(len(stages)))
    parts.append(f'<path d="{d}" fill="none" stroke="{t["link"]}" stroke-width="1.8"/>')
    for i, stage in enumerate(stages):
        _dot(parts, t, xs[i], Y(scores[i]), 5, t["link"], True, _hit(opt["highlights"], stage.get("name")))
        parts.append(
            f'<text x="{xs[i]:.1f}" y="{oy + ph + 18:.1f}" font-size="12" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(stage.get("name") or "", 12))}</text>')
        if stage.get("note"):
            parts.append(
                f'<text x="{xs[i]:.1f}" y="{oy + ph + 34:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="middle">{esc(_short(stage["note"], 16))}</text>')
    return _done(parts, opt, W, H, len(stages), "score 0 to 5")


def _c_story(spec, rows, opt):
    spec = _json(spec)
    backbone = spec.get("backbone") or []
    releases = spec.get("releases") or []
    if not backbone and not releases:
        raise SystemExit("story needs a backbone or releases")
    hh = _hh(opt["title"], opt["sub"])
    W = max(760, 80 + max(len(backbone), 1) * 140)
    H = int(hh + 80 + max(len(releases), 1) * 70 + 40)
    parts, _ = _fig_open(opt["t"], opt["title"], opt["sub"], W, H)
    t = opt["t"]
    for i, name in enumerate(backbone):
        x = 40 + i * 140
        parts.append(f'<rect x="{x:.1f}" y="{hh + 16:.1f}" width="120" height="36" rx="2" fill="{t["ink"]}"/>')
        parts.append(
            f'<text x="{x + 60:.1f}" y="{hh + 39:.1f}" font-size="12" font-family="{FONT}" fill="{t["paper"]}" text-anchor="middle">{esc(_short(name, 14))}</text>')
        if i < len(backbone) - 1:
            parts.append(f'<line x1="{x + 120:.1f}" y1="{hh + 34:.1f}" x2="{x + 140:.1f}" y2="{hh + 34:.1f}" stroke="{t["muted"]}"/>')
    pal = series_palette(t)
    for i, rel in enumerate(releases):
        y = hh + 80 + i * 64
        col = pal[i % len(pal)]
        parts.append(
            f'<text x="36" y="{y + 18:.1f}" font-size="12" font-family="{FONT}" fill="{t["ink"]}">{esc(_short(rel.get("name") or "", 10))}</text>')
        for j, story in enumerate(rel.get("stories") or []):
            x = 120 + j * 130
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="116" height="32" rx="2" fill="{col}" fill-opacity="0.85"/>')
            parts.append(
                f'<text x="{x + 58:.1f}" y="{y + 21:.1f}" font-size="11" font-family="{FONT}" fill="{t["card"]}" text-anchor="middle">{esc(_short(story, 14))}</text>')
    return _done(parts, opt, W, H, len(backbone) + len(releases))


def _c_venn(spec, rows, opt):
    spec = _json(spec)
    sets = spec.get("sets") or []
    if len(sets) not in (2, 3):
        raise SystemExit("venn needs 2 or 3 sets")
    overlap = spec.get("overlap")
    hh = _hh(opt["title"], opt["sub"])
    W, H = 760, hh + 420
    parts, _ = _fig_open(opt["t"], opt["title"], opt["sub"], W, H)
    t = opt["t"]
    pal = series_palette(t)
    cy = hh + 210
    if len(sets) == 2:
        centers = [(300, cy), (460, cy)]
        r = 120
    else:
        centers = [(380, cy - 50), (300, cy + 70), (460, cy + 70)]
        r = 110
    for i, (x, y) in enumerate(centers):
        parts.append(
            f'<circle cx="{x}" cy="{y}" r="{r}" fill="{pal[i % len(pal)]}" fill-opacity="0.28" stroke="{pal[i % len(pal)]}" stroke-width="1.6"/>')
        parts.append(
            f'<text x="{x}" y="{y + (4 if len(sets) == 3 and i == 0 else -r + 28 if i == 0 or len(sets) == 2 else 8)}" font-size="14" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(_short(sets[i].get("name") or "", 12))}</text>')
        if sets[i].get("size") is not None and opt["markers"]:
            parts.append(
                f'<text x="{x}" y="{y + 22:.1f}" font-size="12" font-family="{FONT}" fill="{t["muted"]}" text-anchor="middle">{esc(sets[i]["size"])}</text>')
    if len(sets) == 2 and overlap is not None:
        parts.append(
            f'<text x="380" y="{cy + 4}" font-size="14" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(overlap)}</text>')
    elif isinstance(overlap, dict):
        spots = {"ab": (340, cy + 10), "ac": (420, cy + 10), "bc": (380, cy + 78), "abc": (380, cy + 36)}
        for key, (x, y) in spots.items():
            if overlap.get(key) is not None:
                parts.append(
                    f'<text x="{x}" y="{y}" font-size="13" font-family="{FONT}" fill="{t["ink"]}" text-anchor="middle">{esc(overlap[key])}</text>')
    return _done(parts, opt, W, H, len(sets))


def _polys_from(spec, opt):
    feats = []
    if isinstance(spec, dict):
        feats = spec.get("features") or ([] if spec.get("type") != "Feature" else [spec])
    key = opt.get("val") or "value"
    polys, samples = [], []
    for feat in feats:
        geom = feat.get("geometry") or {}
        props = feat.get("properties") or {}
        try:
            val = float(props.get(key if key in props else "value") or 0)
        except (TypeError, ValueError):
            val = 0
        rings = []
        if geom.get("type") == "Polygon":
            rings = geom.get("coordinates") or []
        elif geom.get("type") == "MultiPolygon":
            rings = [p[0] for p in geom.get("coordinates") or [] if p]
        for ring in rings[:1] if geom.get("type") == "MultiPolygon" else rings[:1]:
            pts = [(c[0], c[1]) for c in ring if isinstance(c, (list, tuple)) and len(c) >= 2]
            if len(pts) >= 3:
                polys.append((pts, val, str(props.get("name") or "")))
                samples.extend(pts)
    if not samples:
        raise SystemExit("choropleth needs GeoJSON polygons")
    return polys, samples


def _c_choropleth(spec, rows, opt):
    spec = _json(spec)
    polys, samples = _polys_from(spec, opt)
    _cap(spec, len(polys), 80, "polygons", _open_budget(spec, opt["unbounded"]))
    ctx = _map_stage(opt["t"], opt["title"], opt["sub"], samples)
    vals = [v for _, v, _ in polys]
    lo, hi = min(vals), max(vals)
    proj = ctx["proj"]
    for pts, val, name in polys:
        clipped = _clip_poly(pts, ctx["minlon"], ctx["minlat"], ctx["maxlon"], ctx["maxlat"])
        if len(clipped) < 3:
            continue
        u = 0.5 if hi == lo else (val - lo) / (hi - lo)
        seq = []
        for lon, lat in clipped:
            x, y = proj(lon, lat)
            seq.append(f"{x:.1f},{y:.1f}")
        ctx["parts"].append(
            f'<polygon points="{" ".join(seq)}" fill="{_heat_color(opt["t"], u)}" fill-opacity="0.82" stroke="{opt["t"]["ink"]}" stroke-width="0.6"/>')
        if name and len(polys) <= 12 and opt["markers"]:
            xs = [proj(p[0], p[1])[0] for p in pts]
            ys = [proj(p[0], p[1])[1] for p in pts]
            ctx["parts"].append(
                f'<text x="{sum(xs) / len(xs):.1f}" y="{sum(ys) / len(ys):.1f}" font-size="11" font-family="{FONT}" fill="{opt["t"]["ink"]}" text-anchor="middle">{esc(_short(name, 14))}</text>')
    ctx["after"] = []
    _ramp(ctx["after"], opt["t"], ctx["ox"], ctx["oy"] + 420 + 6, 130, fmt_tick(lo), fmt_tick(hi))
    svg, W, H = _map_finish(ctx, _foot(opt, len(polys)))
    return svg, W, H, len(polys)


def _geo_rows(rows, opt, need_val=False):
    pairs = [("lat", opt["y"]), ("lon", opt["x"])]
    if need_val:
        pairs.append(("val", opt["val"]))
    return _need(rows, pairs)


def _c_heatgeo(spec, rows, opt):
    c = _geo_rows(rows, opt, True)
    pts = []
    for r in rows:
        try:
            lat, lon, val = _f(r, c["lat"]), _f(r, c["lon"]), _f(r, c["val"])
        except (TypeError, ValueError):
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            pts.append((lon, lat, val))
    if not pts:
        raise SystemExit("heatgeo needs lat, lon, and val")
    _cap(None, len(pts), 400, "points", opt["unbounded"])
    ctx = _map_stage(opt["t"], opt["title"], opt["sub"], [(p[0], p[1]) for p in pts])
    nx = ny = 14
    bins = [[[] for _ in range(nx)] for _ in range(ny)]
    minlon, maxlon = ctx["minlon"], ctx["maxlon"]
    minlat, maxlat = ctx["minlat"], ctx["maxlat"]
    for lon, lat, val in pts:
        i = min(nx - 1, max(0, int((lon - minlon) / ((maxlon - minlon) or 1) * nx)))
        j = min(ny - 1, max(0, int((lat - minlat) / ((maxlat - minlat) or 1) * ny)))
        bins[j][i].append(val)
    flat = [sum(cell) / len(cell) for row in bins for cell in row if cell]
    lo, hi = (min(flat), max(flat)) if flat else (0, 1)
    proj = ctx["proj"]
    for j in range(ny):
        for i in range(nx):
            if not bins[j][i]:
                continue
            v = sum(bins[j][i]) / len(bins[j][i])
            u = 0.5 if hi == lo else (v - lo) / (hi - lo)
            lon0 = minlon + (maxlon - minlon) * i / nx
            lon1 = minlon + (maxlon - minlon) * (i + 1) / nx
            lat0 = minlat + (maxlat - minlat) * j / ny
            lat1 = minlat + (maxlat - minlat) * (j + 1) / ny
            x0, y0 = proj(lon0, lat1)
            x1, y1 = proj(lon1, lat0)
            ctx["parts"].append(
                f'<rect x="{min(x0, x1):.1f}" y="{min(y0, y1):.1f}" width="{abs(x1 - x0):.1f}" height="{abs(y1 - y0):.1f}" fill="{_heat_color(opt["t"], u)}" fill-opacity="0.55"/>')
    ctx["after"] = []
    _ramp(ctx["after"], opt["t"], ctx["ox"], ctx["oy"] + 426, 130, fmt_tick(lo), fmt_tick(hi))
    svg, W, H = _map_finish(ctx, _foot(opt, len(pts)))
    return svg, W, H, len(pts)


def _c_od(spec, rows, opt):
    import math
    c = _need(rows, [("lon", opt["x"]), ("lat", opt["y"]), ("lon2", opt["a"]), ("lat2", opt["b"])])
    vc = _col(rows, opt["val"], "val")
    arcs = []
    samples = []
    for r in rows:
        try:
            lon, lat = _f(r, c["lon"]), _f(r, c["lat"])
            lon2, lat2 = _f(r, c["lon2"]), _f(r, c["lat2"])
            val = _f(r, vc) if vc else 1
        except (TypeError, ValueError):
            continue
        arcs.append((lon, lat, lon2, lat2, val))
        samples.append((lon, lat))
        samples.append((lon2, lat2))
    if not arcs:
        raise SystemExit("od needs lon, lat, lon2, lat2")
    _cap(None, len(arcs), 40, "arcs", opt["unbounded"])
    ctx = _map_stage(opt["t"], opt["title"], opt["sub"], samples)
    ctx["parts"].append(markers(opt["t"]))
    proj = ctx["proj"]
    peak = max(a[4] for a in arcs) or 1
    for lon, lat, lon2, lat2, val in arcs:
        x1, y1 = proj(lon, lat)
        x2, y2 = proj(lon2, lat2)
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1
        mx, my = (x1 + x2) / 2 - dy / length * min(36, length * 0.2), (y1 + y2) / 2 + dx / length * min(36, length * 0.2)
        width = 1.2 + 4.5 * (val / peak)
        ctx["parts"].append(
            f'<path d="M {x1:.1f} {y1:.1f} Q {mx:.1f} {my:.1f} {x2:.1f} {y2:.1f}" fill="none" stroke="{opt["t"]["accent"]}" stroke-width="{width:.1f}" stroke-opacity="0.8" marker-end="url(#aa)"/>')
    svg, W, H = _map_finish(ctx, _foot(opt, len(arcs)))
    return svg, W, H, len(arcs)


def _c_cluster(spec, rows, opt):
    import math
    c = _geo_rows(rows, opt, False)
    pts = []
    for r in rows:
        try:
            lat, lon = _f(r, c["lat"]), _f(r, c["lon"])
        except (TypeError, ValueError):
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            pts.append((lon, lat))
    if not pts:
        raise SystemExit("cluster needs lat and lon")
    _cap(None, len(pts), 400, "points", opt["unbounded"])
    ctx = _map_stage(opt["t"], opt["title"], opt["sub"], pts)
    span = max(ctx["maxlon"] - ctx["minlon"], ctx["maxlat"] - ctx["minlat"]) or 1
    cell = span / 10
    buckets = {}
    for lon, lat in pts:
        key = (round(lon / cell), round(lat / cell))
        buckets.setdefault(key, []).append((lon, lat))
    peak = max(len(v) for v in buckets.values())
    proj = ctx["proj"]
    ranked = sorted(buckets.values(), key=len, reverse=True)
    for group in buckets.values():
        lon = sum(p[0] for p in group) / len(group)
        lat = sum(p[1] for p in group) / len(group)
        x, y = proj(lon, lat)
        rad = 6 + 14 * math.sqrt(len(group) / peak)
        ctx["parts"].append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad:.1f}" fill="{opt["t"]["link"]}" fill-opacity="0.75" stroke="{opt["t"]["card"]}"/>')
        if opt["markers"] and group in ranked[:5]:
            ctx["parts"].append(
                f'<text x="{x:.1f}" y="{y + 4:.1f}" font-size="11" font-family="{FONT}" fill="{opt["t"]["card"]}" text-anchor="middle">{len(group)}</text>')
    svg, W, H = _map_finish(ctx, _foot(opt, len(pts), f"{len(buckets)} clusters"))
    return svg, W, H, len(pts)


def _math_prep(src):
    """Turn a small slice of calculator and LaTeX spelling into plain tokens."""
    s = str(src).strip().replace("π", "pi").replace("τ", "tau")
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("\\,", "").replace("\\;", "").replace("\\!", "").replace("\\ ", "")
    s = s.replace("\\cdot", "*").replace("\\times", "*").replace("\\pi", "pi").replace("\\tau", "tau")
    while True:
        i, j = s.find("\\frac"), s.find("\\sqrt")
        if i < 0 and j < 0:
            break
        if i >= 0 and (j < 0 or i < j):
            k = i + 5
            num, k = _math_braced(s, k)
            den, k = _math_braced(s, k)
            s = s[:i] + "((" + num + ")/(" + den + "))" + s[k:]
        else:
            k = j + 5
            body, k = _math_braced(s, k)
            s = s[:j] + "(sqrt(" + body + "))" + s[k:]
    import re
    s = re.sub(r"\\([A-Za-z]+)", r"\1", s)
    return s


def _math_braced(s, i):
    if i >= len(s) or s[i] != "{":
        raise ValueError("expected { }")
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
    raise ValueError("unbalanced braces")


def _math_lex(s):
    toks, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c.isspace():
            i += 1
            continue
        if c.isdigit() or (c == "." and i + 1 < n and s[i + 1].isdigit()):
            j = i + 1
            while j < n and (s[j].isdigit() or s[j] == "."):
                j += 1
            if j < n and s[j] in "eE":
                k = j + 1
                if k < n and s[k] in "+-":
                    k += 1
                if k < n and s[k].isdigit():
                    k += 1
                    while k < n and s[k].isdigit():
                        k += 1
                    j = k
            try:
                toks.append(("num", float(s[i:j])))
            except ValueError as exc:
                raise ValueError(f"bad number {s[i:j]}") from exc
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i + 1
            while j < n and (s[j].isalnum() or s[j] == "_"):
                j += 1
            toks.append(("id", s[i:j]))
            i = j
            continue
        if c in "<>" and i + 1 < n and s[i + 1] == "=":
            toks.append(("op", c + "="))
            i += 2
            continue
        if c == "*" and i + 1 < n and s[i + 1] == "*":
            toks.append(("op", "^"))
            i += 2
            continue
        if c in "+-*/^=<>(),|":
            toks.append(("op", c))
            i += 1
            continue
        raise ValueError(f"unexpected {c!r}")
    return toks


_MATH_CONST = None
_MATH_FUNCS = None


def _math_tables():
    import math
    global _MATH_CONST, _MATH_FUNCS
    if _MATH_FUNCS:
        return _MATH_CONST, _MATH_FUNCS

    def cbrt(v):
        return math.copysign(abs(v) ** (1.0 / 3.0), v)

    def sign(v):
        return float((v > 0) - (v < 0))

    _MATH_CONST = {"pi": math.pi, "e": math.e, "tau": math.tau}
    _MATH_FUNCS = {
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "asin": math.asin, "acos": math.acos, "atan": math.atan, "atan2": math.atan2,
        "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
        "sqrt": math.sqrt, "cbrt": cbrt, "abs": abs, "fabs": abs,
        "floor": math.floor, "ceil": math.ceil, "round": lambda v: float(round(v)),
        "sign": sign, "ln": math.log, "log10": math.log10, "log2": math.log2,
        "exp": math.exp, "min": min, "max": max, "hypot": math.hypot,
    }
    return _MATH_CONST, _MATH_FUNCS


class _MathParse:
    def __init__(self, toks):
        self.toks, self.k = toks, 0

    def peek(self):
        return self.toks[self.k] if self.k < len(self.toks) else None

    def pop(self):
        tok = self.peek()
        if tok is None:
            raise ValueError("unexpected end")
        self.k += 1
        return tok

    def parse(self):
        node = self.comparison()
        if self.peek() is not None:
            raise ValueError(f"unexpected {self.peek()[1]!r}")
        return node

    def comparison(self):
        left = self.add()
        tok = self.peek()
        if tok and tok[0] == "op" and tok[1] in ("=", "<", ">", "<=", ">="):
            op = self.pop()[1]
            return ("rel", op, left, self.add())
        return left

    def add(self):
        left = self.mul()
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.pop()[1]
            left = ("bin", op, left, self.mul())
        return left

    def mul(self):
        # Juxtaposition binds tighter than * and /, so 1/2x is 1/(2x).
        left = self.jux()
        while self.peek() in (("op", "*"), ("op", "/")):
            op = self.pop()[1]
            left = ("bin", op, left, self.jux())
        return left

    def jux(self):
        left = self.unary()
        while self._jux():
            left = ("bin", "*", left, self.unary())
        return left

    def _jux(self):
        tok = self.peek()
        if tok is None or tok[0] == "num":
            return False
        if tok[0] == "id":
            return True
        return tok in (("op", "("), ("op", "|"))

    def unary(self):
        if self.peek() in (("op", "+"), ("op", "-")):
            op = self.pop()[1]
            node = self.unary()
            return node if op == "+" else ("neg", node)
        consts, funcs = _math_tables()
        tok = self.peek()
        if tok and tok[0] == "id" and tok[1] in funcs:
            name = self.pop()[1]
            if self.peek() == ("op", "^") and self.k + 1 < len(self.toks) and self.toks[self.k + 1][0] == "num":
                self.pop()
                exp = self.pop()[1]
                return ("bin", "^", ("call", name, [self.unary()]), ("num", exp))
            return ("call", name, [self.unary()] if self.peek() != ("op", "(") else self.args())
        return self.power()

    def args(self):
        self.pop()
        out = [self.add()]
        while self.peek() == ("op", ","):
            self.pop()
            out.append(self.add())
        if self.pop() != ("op", ")"):
            raise ValueError("expected )")
        return out

    def power(self):
        base = self.primary()
        if self.peek() == ("op", "^"):
            self.pop()
            return ("bin", "^", base, self.unary())
        return base

    def primary(self):
        tok = self.pop()
        consts, funcs = _math_tables()
        if tok[0] == "num":
            return ("num", tok[1])
        if tok[0] == "id":
            if tok[1] in consts:
                return ("num", consts[tok[1]])
            if tok[1] in ("x", "y", "t", "u"):
                return ("var", tok[1])
            if tok[1] in funcs:
                raise ValueError(f"{tok[1]} needs an argument")
            raise ValueError(f"unknown name {tok[1]}")
        if tok == ("op", "("):
            node = self.comparison()
            if self.pop() != ("op", ")"):
                raise ValueError("expected )")
            return node
        if tok == ("op", "|"):
            node = self.add()
            if self.pop() != ("op", "|"):
                raise ValueError("expected |")
            return ("abs", node)
        raise ValueError(f"unexpected {tok[1]!r}")


def _math_parse(src):
    return _MathParse(_math_lex(_math_prep(src))).parse()


def _math_vars(node, acc=None):
    acc = set() if acc is None else acc
    kind = node[0]
    if kind == "var":
        acc.add(node[1])
    elif kind in ("neg", "abs"):
        _math_vars(node[1], acc)
    elif kind in ("bin", "rel"):
        _math_vars(node[2], acc)
        _math_vars(node[3], acc)
    elif kind == "call":
        for arg in node[2]:
            _math_vars(arg, acc)
    return acc


def _math_value(node, env, depth=0):
    if depth > 64:
        return None
    try:
        return _math_eval(node, env, depth)
    except (ValueError, ZeroDivisionError, OverflowError, ArithmeticError):
        return None


def _math_eval(node, env, depth):
    import math
    kind = node[0]
    if kind == "num":
        return float(node[1])
    if kind == "var":
        return float(env[node[1]])
    if kind == "neg":
        return -_math_eval(node[1], env, depth + 1)
    if kind == "abs":
        return abs(_math_eval(node[1], env, depth + 1))
    if kind == "bin":
        a = _math_eval(node[2], env, depth + 1)
        b = _math_eval(node[3], env, depth + 1)
        op = node[1]
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            if b == 0:
                return None
            return a / b
        if a < 0 and abs(b - round(b)) > 1e-9:
            return None
        return math.pow(a, b) if abs(a) > 1e-12 or b >= 0 else None
    if kind == "call":
        args = [_math_eval(a, env, depth + 1) for a in node[2]]
        name = node[1]
        if name == "log":
            if len(args) == 1:
                return math.log10(args[0])
            if len(args) == 2 and args[1] not in (0, 1, -1) and args[0] > 0 and args[1] > 0:
                return math.log(args[0]) / math.log(args[1])
            return None
        fn = _math_tables()[1][name]
        return float(fn(*args))
    return None


def _math_const(node):
    if _math_vars(node):
        raise ValueError("bounds must be numbers")
    value = _math_value(node, {})
    if value is None:
        raise ValueError("bounds must be numbers")
    return value


def _math_peel_for(src):
    import re
    match = re.search(r"^(.*?)\s+\bfor\s+([A-Za-z])\s+in\s*\[\s*([^,\]]+?)\s*,\s*([^\]]+?)\s*\]\s*$", src.strip())
    if not match:
        return src.strip(), None, None, None
    return match.group(1).strip(), match.group(2), match.group(3).strip(), match.group(4).strip()


def _math_pair(src):
    if not src.startswith("("):
        return None
    depth, comma = 0, None
    for i, ch in enumerate(src):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                if i != len(src) - 1:
                    return None
                break
        elif ch == "," and depth == 1 and comma is None:
            comma = i
    if depth != 0 or comma is None:
        return None
    return src[1:comma].strip(), src[comma + 1:-1].strip()


def _math_compile_item(item):
    if isinstance(item, str):
        item = {"expr": item}
    if not isinstance(item, dict) or not str(item.get("expr") or "").strip():
        raise ValueError("an equation needs expr")
    original = str(item["expr"]).strip()
    try:
        body, param, lo_s, hi_s = _math_peel_for(original)
        pair = _math_pair(_math_prep(body))
        if pair:
            left, right = _math_parse(pair[0]), _math_parse(pair[1])
            if param:
                names = {param}
                t0, t1 = _math_const(_math_parse(lo_s)), _math_const(_math_parse(hi_s))
            else:
                used = _math_vars(left) | _math_vars(right)
                names = used & {"t", "u", "x"}
                t0 = float(item["tmin"]) if "tmin" in item else 0.0
                t1 = float(item["tmax"]) if "tmax" in item else (2 * _math_tables()[0]["pi"])
            if len(names) > 1:
                raise ValueError("a parametric curve uses one parameter")
            name = item.get("name") or original
            if not names:
                return {"kind": "point", "x": _math_const(left), "y": _math_const(right),
                        "name": name, "expr": original, "focal": bool(item.get("focal"))}
            return {"kind": "parametric", "x": left, "y": right, "param": names.pop(),
                    "tmin": t0, "tmax": t1, "name": name, "expr": original, "focal": bool(item.get("focal"))}
        node = _math_parse(body)
    except ValueError as exc:
        raise ValueError(f"cannot read {original}: {exc}") from None
    name = item.get("name") or original
    focal = bool(item.get("focal"))
    if node[0] == "rel":
        op, lhs, rhs = node[1], node[2], node[3]
        diff = ("bin", "-", lhs, rhs)
        if lhs == ("var", "y") and "y" not in _math_vars(rhs):
            kind = "explicit" if op == "=" else "ineq"
            return {"kind": kind, "var": "x", "fn": rhs, "op": op, "diff": diff,
                    "name": name, "expr": original, "focal": focal}
        if lhs == ("var", "x") and "x" not in _math_vars(rhs):
            if op != "=":
                raise ValueError(f"cannot read {original}: inequality in x is not drawn")
            return {"kind": "explicit", "var": "y", "fn": rhs, "op": op, "diff": diff,
                    "name": name, "expr": original, "focal": focal}
        if op == "=":
            return {"kind": "implicit", "diff": diff, "name": name, "expr": original, "focal": focal}
        return {"kind": "region", "diff": diff, "op": op, "name": name, "expr": original, "focal": focal}
    used = _math_vars(node)
    if "y" not in used:
        return {"kind": "explicit", "var": "x", "fn": node, "op": "=", "name": name, "expr": original, "focal": focal}
    if "x" not in used:
        return {"kind": "explicit", "var": "y", "fn": node, "op": "=", "name": name, "expr": original, "focal": focal}
    return {"kind": "implicit", "diff": node, "name": name, "expr": original, "focal": focal}


def _math_items(spec):
    if not isinstance(spec, dict):
        raise ValueError("math spec must be a JSON object")
    raw = spec.get("equations", spec.get("expr"))
    if isinstance(raw, str):
        raw = [raw]
    raw = list(raw or [])
    if not raw and not spec.get("points"):
        raise ValueError("math needs an equation")
    return raw


def _math_from_text(path):
    spec = {"equations": []}
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, val = line.partition("=")
            if sep and key.strip() in ("xmin", "xmax", "ymin", "ymax", "samples", "title", "sub", "equal"):
                key, val = key.strip(), val.strip()
                if key == "equal":
                    spec[key] = val.lower() in ("1", "true", "yes")
                elif key in ("title", "sub"):
                    spec[key] = val
                else:
                    spec[key] = float(val)
                continue
            spec["equations"].append(line)
    if not spec["equations"]:
        raise ValueError("math needs an equation")
    return spec


def _math_call(fn_node, var, value):
    env = {"x": 0.0, "y": 0.0, "t": 0.0, "u": 0.0, var: value}
    value = _math_value(fn_node, env)
    if value is None or value != value or abs(value) > 1e6:
        return None
    return value


def _math_field(node, x, y):
    value = _math_value(node, {"x": x, "y": y, "t": 0.0, "u": 0.0})
    if value is None or value != value or abs(value) > 1e6:
        return None
    return value


def _math_sample(fn_node, var, lo, hi, n):
    n = max(48, min(int(n or 360), 1600))
    xs = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    ys = [_math_call(fn_node, var, x) for x in xs]
    rx, ry = [xs[0]], [ys[0]]
    for i in range(n - 1):
        y1, y2 = ys[i], ys[i + 1]
        mid = _math_call(fn_node, var, (xs[i] + xs[i + 1]) / 2)
        if y1 is not None and y2 is not None and mid is not None:
            chord = abs(mid - (y1 + y2) / 2)
            if chord > 0.015 * max(1.0, abs(y1), abs(y2), abs(mid)):
                rx.append((xs[i] + xs[i + 1]) / 2)
                ry.append(mid)
        rx.append(xs[i + 1])
        ry.append(ys[i + 1])
    lines, cur = [], []
    for x, y in zip(rx, ry):
        if y is None:
            if len(cur) > 1:
                lines.append(cur)
            cur = []
            continue
        if cur:
            y0 = cur[-1][1]
            if y0 * y < 0 and abs(y0) > 8 and abs(y) > 8:
                mid = _math_call(fn_node, var, (cur[-1][0] + x) / 2)
                if mid is None or abs(mid) > max(abs(y0), abs(y)):
                    if len(cur) > 1:
                        lines.append(cur)
                    cur = [(x, y)]
                    continue
        cur.append((x, y))
    if len(cur) > 1:
        lines.append(cur)
    if var == "y":
        lines = [[(y, x) for x, y in line] for line in lines]
    return lines


def _math_clip_seg(x1, y1, x2, y2, xmin, xmax, ymin, ymax):
    dx, dy = x2 - x1, y2 - y1
    u1, u2 = 0.0, 1.0
    for pi, qi in ((-dx, x1 - xmin), (dx, xmax - x1), (-dy, y1 - ymin), (dy, ymax - y1)):
        if abs(pi) < 1e-15:
            if qi < 0:
                return None
            continue
        t = qi / pi
        if pi < 0:
            if t > u2:
                return None
            u1 = max(u1, t)
        else:
            if t < u1:
                return None
            u2 = min(u2, t)
    if u1 > u2:
        return None
    return (x1 + u1 * dx, y1 + u1 * dy, x1 + u2 * dx, y1 + u2 * dy)


def _math_clip_chain(pts, box):
    xmin, xmax, ymin, ymax = box
    out, cur = [], []
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        hit = _math_clip_seg(x1, y1, x2, y2, xmin, xmax, ymin, ymax)
        if not hit:
            if len(cur) > 1:
                out.append(cur)
            cur = []
            continue
        a, b = (hit[0], hit[1]), (hit[2], hit[3])
        if not cur or abs(a[0] - cur[-1][0]) > 1e-7 or abs(a[1] - cur[-1][1]) > 1e-7:
            if len(cur) > 1:
                out.append(cur)
            cur = [a, b]
        else:
            cur.append(b)
    if len(cur) > 1:
        out.append(cur)
    return out


def _math_march(diff, xmin, xmax, ymin, ymax, n=72):
    xs = [xmin + (xmax - xmin) * i / n for i in range(n + 1)]
    ys = [ymin + (ymax - ymin) * j / n for j in range(n + 1)]
    grid = [[_math_field(diff, xs[i], ys[j]) for i in range(n + 1)] for j in range(n + 1)]
    segs = []

    def cross(p, q, vp, vq):
        if vp is None or vq is None or vp == vq:
            t = 0.5
        else:
            t = vp / (vp - vq)
        t = max(0.0, min(1.0, t))
        return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)

    for j in range(n):
        for i in range(n):
            corners = (grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i])
            if any(v is None for v in corners):
                continue
            bit = (1 if corners[0] < 0 else 0) | (2 if corners[1] < 0 else 0)
            bit |= (4 if corners[2] < 0 else 0) | (8 if corners[3] < 0 else 0)
            if bit in (0, 15):
                continue
            sw, se = (xs[i], ys[j]), (xs[i + 1], ys[j])
            ne, nw = (xs[i + 1], ys[j + 1]), (xs[i], ys[j + 1])
            edge = {
                "B": cross(sw, se, corners[0], corners[1]),
                "R": cross(se, ne, corners[1], corners[2]),
                "T": cross(ne, nw, corners[2], corners[3]),
                "L": cross(nw, sw, corners[3], corners[0]),
            }
            pairs = {
                1: [("L", "B")], 2: [("B", "R")], 3: [("L", "R")], 4: [("R", "T")],
                6: [("B", "T")], 7: [("L", "T")], 8: [("T", "L")], 9: [("B", "T")],
                11: [("R", "T")], 12: [("R", "L")], 13: [("B", "R")], 14: [("L", "B")],
            }.get(bit)
            if bit in (5, 10):
                center = _math_field(diff, (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2)
                neg = center is not None and center < 0
                pairs = [("L", "B"), ("R", "T")] if (bit == 5) == neg else [("B", "R"), ("T", "L")]
                if bit == 10:
                    pairs = [("B", "L"), ("T", "R")] if neg else [("L", "T"), ("R", "B")]
            for a, b in pairs or []:
                segs.append((edge[a], edge[b]))
    return _math_stitch(segs)


def _math_stitch(segs):
    def key(pt):
        return (round(pt[0], 5), round(pt[1], 5))

    adj, edges = {}, {}
    for a, b in segs:
        edges[(key(a), key(b)) if key(a) <= key(b) else (key(b), key(a))] = (a, b)
        adj.setdefault(key(a), []).append(b)
        adj.setdefault(key(b), []).append(a)
    unused = set(edges)
    lines = []
    while unused:
        start = unused.pop()
        a, b = edges[start]
        chain = [a, b]
        for end in (0, -1):
            while True:
                tip = chain[end]
                nxt = None
                for nb in adj.get(key(tip), []):
                    mark = (key(tip), key(nb)) if key(tip) <= key(nb) else (key(nb), key(tip))
                    if mark in unused:
                        unused.remove(mark)
                        nxt = nb
                        break
                if nxt is None:
                    break
                if end == 0:
                    chain.insert(0, nxt)
                else:
                    chain.append(nxt)
        if len(chain) > 1:
            lines.append(chain)
    return lines


def _math_runs(pred, xmin, xmax, ymin, ymax, n=64):
    strips = []
    for j in range(n):
        y0 = ymin + (ymax - ymin) * j / n
        y1 = ymin + (ymax - ymin) * (j + 1) / n
        yc = (y0 + y1) / 2
        run = None
        for i in range(n + 1):
            inside = False
            if i < n:
                xc = xmin + (xmax - xmin) * (i + 0.5) / n
                inside = bool(pred(xc, yc))
            if inside and run is None:
                run = i
            if not inside and run is not None:
                strips.append((xmin + (xmax - xmin) * run / n, y0,
                               xmin + (xmax - xmin) * i / n, y1))
                run = None
    return strips


def _math_pct(vals, p):
    if not vals:
        return None
    ordered = sorted(vals)
    idx = (len(ordered) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def _math_trace(curve, xmin, xmax, ymin, ymax, samples):
    """Sample a curve on the final window. Returns y values used to autoscale."""
    curve.pop("lines", None)
    if curve["kind"] in ("explicit", "ineq"):
        if curve["var"] == "x":
            lines = _math_sample(curve["fn"], "x", xmin, xmax, samples)
        else:
            lines = _math_sample(curve["fn"], "y", ymin, ymax, samples)
        curve["lines"] = lines
        return [pt[1] for line in lines for pt in line]
    if curve["kind"] != "parametric":
        return []
    t0, t1 = float(curve["tmin"]), float(curve["tmax"])
    if t1 < t0:
        t0, t1 = t1, t0
    count = max(48, min(int(samples or 360), 1600))
    pts, lines = [], []
    for i in range(count):
        t = t0 + (t1 - t0) * i / (count - 1)
        x = _math_call(curve["x"], curve["param"], t)
        y = _math_call(curve["y"], curve["param"], t)
        if x is None or y is None:
            if len(pts) > 1:
                lines.append(pts)
            pts = []
            continue
        pts.append((x, y))
    if len(pts) > 1:
        lines.append(pts)
    curve["lines"] = lines
    return [pt[1] for line in lines for pt in line]


def _c_math(spec, rows, opt):
    spec = spec if isinstance(spec, dict) else {}
    opt = dict(opt, spec=spec)
    try:
        curves = [_math_compile_item(item) for item in _math_items(spec)]
    except ValueError as exc:
        raise SystemExit(str(exc))
    _cap(spec, len(curves), 8, "equations", opt["unbounded"])
    if sum(1 for c in curves if c.get("focal")) > 2:
        raise SystemExit("focal on >2 equations. Keep one or two.")
    samples = int(spec.get("samples") or 360)
    xmin = spec.get("xmin", -10)
    xmax = spec.get("xmax", 10)
    try:
        xmin, xmax = float(xmin), float(xmax)
    except (TypeError, ValueError):
        raise SystemExit("xmin and xmax must be numbers")
    if xmax <= xmin:
        raise SystemExit("xmax must be greater than xmin")
    probe = []
    y_probe_lo = float(spec["ymin"]) if spec.get("ymin") is not None else xmin
    y_probe_hi = float(spec["ymax"]) if spec.get("ymax") is not None else xmax
    for curve in curves:
        probe.extend(_math_trace(curve, xmin, xmax, y_probe_lo, y_probe_hi, min(samples, 180)))
    finite = [v for v in probe if v is not None]
    if spec.get("ymin") is None or spec.get("ymax") is None:
        if finite:
            ymin, ymax = _math_pct(finite, 0.02), _math_pct(finite, 0.98)
            span = (ymax - ymin) or 1
            ymin, ymax = ymin - span * 0.08, ymax + span * 0.08
        else:
            ymin, ymax = xmin, xmax
    else:
        ymin, ymax = float(spec["ymin"]), float(spec["ymax"])
    if ymax <= ymin:
        raise SystemExit("ymax must be greater than ymin")
    auto_equal = any(c["kind"] in ("implicit", "region", "parametric", "point") for c in curves)
    equal = spec["equal"] if "equal" in spec else auto_equal
    legend = len(curves) > 1
    parts, t, W, H, ox, oy, pw, ph = _begin(opt, 340, ox=72, right=28, W=780, bottom=86 if legend else 58)
    if equal:
        xmin, xmax, ymin, ymax = _math_equal(xmin, xmax, ymin, ymax, pw, ph)
    for curve in curves:
        _math_trace(curve, xmin, xmax, ymin, ymax, samples)
    xt = [v for v in nice_ticks(xmin, xmax, 8) if xmin - 1e-9 <= v <= xmax + 1e-9] or [xmin, xmax]
    yt = [v for v in nice_ticks(ymin, ymax, 8) if ymin - 1e-9 <= v <= ymax + 1e-9] or [ymin, ymax]
    spanx, spany = (xmax - xmin) or 1, (ymax - ymin) or 1

    def X(v):
        return ox + (v - xmin) / spanx * pw

    def Y(v):
        return oy + ph - (v - ymin) / spany * ph

    parts.append(f'<clipPath id="plotclip"><rect x="{ox}" y="{oy}" width="{pw}" height="{ph}"/></clipPath>')
    if opt["grid"]:
        for v in xt:
            parts.append(f'<line x1="{X(v):.1f}" y1="{oy}" x2="{X(v):.1f}" y2="{oy + ph}" stroke="{t["rule"]}" stroke-width="1"/>')
        for v in yt:
            parts.append(f'<line x1="{ox}" y1="{Y(v):.1f}" x2="{ox + pw}" y2="{Y(v):.1f}" stroke="{t["rule"]}" stroke-width="1"/>')
    parts.append(f'<rect x="{ox}" y="{oy}" width="{pw}" height="{ph}" fill="none" stroke="{t["ink"]}" stroke-width="1"/>')
    x_axis = 0 if xmin < 0 < xmax else xmin
    y_axis = 0 if ymin < 0 < ymax else ymin
    parts.append(f'<line x1="{ox}" y1="{Y(y_axis):.1f}" x2="{ox + pw}" y2="{Y(y_axis):.1f}" stroke="{t["ink"]}" stroke-width="1.3"/>')
    parts.append(f'<line x1="{X(x_axis):.1f}" y1="{oy}" x2="{X(x_axis):.1f}" y2="{oy + ph}" stroke="{t["ink"]}" stroke-width="1.3"/>')
    for v in xt:
        if abs(v) < 1e-9 and xmin < 0 < xmax and ymin < 0 < ymax:
            continue
        parts.append(
            f'<text x="{X(v):.1f}" y="{Y(y_axis) + 14:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="middle">{fmt_tick(v)}</text>')
    for v in yt:
        if abs(v) < 1e-9:
            continue
        parts.append(
            f'<text x="{X(x_axis) - 6:.1f}" y="{Y(v) + 3:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">{fmt_tick(v)}</text>')
    if xmin < 0 < xmax and ymin < 0 < ymax:
        parts.append(
            f'<text x="{X(0) - 6:.1f}" y="{Y(0) + 14:.1f}" font-size="10" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">0</text>')
    parts.append(
        f'<text x="{ox + pw - 8:.1f}" y="{Y(y_axis) - 6:.1f}" font-size="11" font-family="{FONT}" fill="{t["muted"]}" text-anchor="end">x</text>')
    parts.append(
        f'<text x="{X(x_axis) + 8:.1f}" y="{oy + 14:.1f}" font-size="11" font-family="{FONT}" fill="{t["muted"]}">y</text>')
    taken = [(ox + pw - 18, Y(y_axis) - 16, ox + pw - 6, Y(y_axis) - 3),
             (X(x_axis) + 6, oy + 4, X(x_axis) + 18, oy + 17)]
    for v in xt:
        tw = _text_w(fmt_tick(v), 10)
        taken.append((X(v) - tw / 2, Y(y_axis) + 6, X(v) + tw / 2, Y(y_axis) + 16))
    for v in yt:
        tw = _text_w(fmt_tick(v), 10)
        taken.append((X(x_axis) - 6 - tw, Y(v) - 5, X(x_axis) - 6, Y(v) + 5))
    box = (xmin, xmax, ymin, ymax)
    pal = series_palette(t)
    parts.append('<g clip-path="url(#plotclip)">')
    legend_items = []
    for i, curve in enumerate(curves):
        col = t["accent"] if curve.get("focal") or _hit(opt["highlights"], curve["name"], curve["expr"]) else pal[i % len(pal)]
        legend_items.append((col, _short(_math_label(curve), 22)))
        if curve["kind"] == "ineq":
            for line in curve.get("lines", []):
                for piece in _math_clip_chain(line, box):
                    floor = ymin if curve["op"] in ("<", "<=") else ymax
                    poly = piece + [(piece[-1][0], floor), (piece[0][0], floor)]
                    d = " ".join(
                        [("M" if n == 0 else "L") + f"{X(p[0]):.1f},{Y(p[1]):.1f}" for n, p in enumerate(poly)]) + " Z"
                    parts.append(f'<path d="{d}" fill="{col}" fill-opacity="0.16" stroke="none"/>')
        if curve["kind"] == "region":
            op = curve["op"]

            def pred(x, y, node=curve["diff"], op=op):
                value = _math_field(node, x, y)
                if value is None:
                    return False
                if op == "<":
                    return value < 0
                if op == "<=":
                    return value <= 0
                if op == ">":
                    return value > 0
                return value >= 0

            for x0, y0, x1, y1 in _math_runs(pred, xmin, xmax, ymin, ymax):
                parts.append(
                    f'<rect x="{X(x0):.1f}" y="{Y(y1):.1f}" width="{max(0.6, X(x1) - X(x0)):.1f}" height="{max(0.6, Y(y0) - Y(y1)):.1f}" fill="{col}" fill-opacity="0.2" stroke="none"/>')
            for line in _math_march(curve["diff"], xmin, xmax, ymin, ymax):
                _math_stroke(parts, line, X, Y, col, 1.4)
        if curve["kind"] == "implicit":
            for line in _math_march(curve["diff"], xmin, xmax, ymin, ymax):
                _math_stroke(parts, line, X, Y, col, 1.8)
        if curve["kind"] in ("explicit", "ineq", "parametric"):
            longest = []
            for line in curve.get("lines", []):
                for piece in _math_clip_chain(line, box):
                    _math_stroke(parts, piece, X, Y, col, 1.8)
                    if len(piece) > len(longest):
                        longest = piece
            if opt["markers"] and longest:
                _math_tag(parts, t, longest, X, Y, ox, oy, pw, ph, _math_label(curve), col, taken)
        if curve["kind"] == "point":
            _dot(parts, t, X(curve["x"]), Y(curve["y"]), 3.4, col, True, curve.get("focal"))
            _math_tag(parts, t, [(curve["x"], curve["y"])], X, Y, ox, oy, pw, ph, _math_label(curve), col, taken)
    for pt in spec.get("points") or []:
        try:
            px, py = float(pt["x"]), float(pt["y"])
        except (TypeError, ValueError, KeyError):
            continue
        if not (xmin <= px <= xmax and ymin <= py <= ymax):
            continue
        _dot(parts, t, X(px), Y(py), 3.4, t["ink"], True, _hit(opt["highlights"], pt.get("name")))
        if pt.get("name"):
            _math_tag(parts, t, [(px, py)], X, Y, ox, oy, pw, ph, str(pt["name"]), t["ink"], taken)
    parts.append("</g>")
    if legend:
        _legend(parts, t, legend_items, ox, oy + ph + 34, ox + pw)
    return _done(parts, opt, W, H, len(curves), "equal scale" if equal else "")


def _math_equal(xmin, xmax, ymin, ymax, pw, ph):
    dx, dy = xmax - xmin, ymax - ymin
    if dx <= 0 or dy <= 0 or pw <= 0 or ph <= 0:
        return xmin, xmax, ymin, ymax
    data, pix = dx / dy, pw / ph
    if abs(data - pix) <= 0.02 * pix:
        return xmin, xmax, ymin, ymax
    if data > pix:
        need = dx / pix
        mid = (ymin + ymax) / 2
        return xmin, xmax, mid - need / 2, mid + need / 2
    need = dy * pix
    mid = (xmin + xmax) / 2
    return mid - need / 2, mid + need / 2, ymin, ymax


def _math_label(curve):
    return str(curve.get("name") or curve.get("expr") or "f").replace("{", "(").replace("}", ")")


def _math_stroke(parts, pts, X, Y, col, width):
    if len(pts) < 2:
        return
    d = " ".join((("M" if i == 0 else "L") + f"{X(p[0]):.1f},{Y(p[1]):.1f}") for i, p in enumerate(pts))
    parts.append(
        f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>')


def _math_tag(parts, t, pts, X, Y, ox, oy, pw, ph, label, col, taken=None):
    """Label a curve near its end. Walk back along the curve until the label sits clear
    of the axis names and the labels already placed."""
    shown = _short(label, 18)
    w = _text_w(shown, 11)
    taken = [] if taken is None else taken
    step = max(1, len(pts) // 12)
    first = None
    for k in range(len(pts) - 1, -1, -step):
        x, y = X(pts[k][0]), Y(pts[k][1])
        if not (ox - 2 <= x <= ox + pw + 2 and oy - 2 <= y <= oy + ph + 2):
            continue
        anchor = "end" if x > ox + pw - 72 else "start"
        tx = x - 6 if anchor == "end" else x + 6
        for ty in (y - 6, y + 16):
            x0 = tx - w if anchor == "end" else tx
            box = (x0, ty - 9, x0 + w, ty + 3)
            if first is None:
                first = (tx, ty, anchor, box)
            if oy <= box[1] and box[3] <= oy + ph and not any(
                    box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in taken):
                first = (tx, ty, anchor, box)
                break
        else:
            continue
        break
    if first is None:
        return
    tx, ty, anchor, box = first
    taken.append(box)
    parts.append(
        f'<text x="{tx:.1f}" y="{ty:.1f}" font-size="11" font-family="{FONT}" fill="{col}" text-anchor="{anchor}">{esc(shown)}</text>')


_CHART_FN = {
    "bubble": _c_bubble, "beeswarm": _c_beeswarm, "step": _c_step, "slope": _c_slope,
    "bump": _c_bump, "ridgeline": _c_ridgeline, "stack": _c_stack, "dumbbell": _c_dumbbell,
    "waterfall": _c_waterfall, "histogram": _c_histogram, "box": _c_box, "violin": _c_violin,
    "strip": _c_strip, "pie": _c_pie, "donut": _c_donut, "waffle": _c_waffle,
    "treemap": _c_treemap, "icicle": _c_icicle, "sunburst": _c_sunburst, "heatmap": _c_heatmap,
    "calendar": _c_calendar, "radar": _c_radar, "polar": _c_polar, "candle": _c_candle,
    "status": _c_status, "forest": _c_forest, "qq": _c_qq, "volcano": _c_volcano,
    "sankey": _c_sankey, "stream": _c_stream, "funnel": _c_funnel, "combo": _c_combo,
    "quadrant": _c_quadrant, "contour": _c_contour, "math": _c_math, "dag": _c_dag, "force": _c_force,
    "radial": _c_radial, "tree": _c_tree, "dtree": _c_dtree, "nested": _c_nested,
    "kg": _c_kg, "context": _c_context, "uml": _c_uml, "deploy": _c_deploy,
    "layers": _c_layers, "integration": _c_integration, "current": _c_current, "er": _c_er,
    "wardley": _c_wardley, "swim": _c_swim, "state": _c_state, "bpmn": _c_bpmn,
    "fishbone": _c_fishbone, "flywheel": _c_flywheel, "kanban": _c_kanban, "gantt": _c_gantt,
    "timeline": _c_timeline, "journey": _c_journey, "story": _c_story, "org": _c_org,
    "venn": _c_venn, "choropleth": _c_choropleth, "heatgeo": _c_heatgeo, "od": _c_od,
    "cluster": _c_cluster,
}


def _render_alias(kind, path, title, subtitle, source, theme, x, y, label, val, grid, markers_on, highlights):
    base = CHART_ALIAS[kind]
    if base == "geo":
        svg, W, H, n = render_geo(path, y, x, label, val, title or "Map", subtitle, "Fig. 1", source, theme,
                                  grid=grid, markers=markers_on, highlights=highlights)
        return svg, W, H, n
    spec = load_spec(path)
    if title:
        spec["title"] = title
    if subtitle:
        spec["sub"] = subtitle
    if base == "flow":
        svg, W, H = render_flow(spec, "editorial", False, theme)
        n = len(spec.get("nodes", []))
    elif base == "arch":
        svg, W, H = render_arch(spec, "editorial", theme)
        n = len(spec.get("nodes", []))
    else:
        svg, W, H = render_seq(spec, "editorial", theme)
        n = len(spec.get("actors", []))
    return svg, W, H, n


def render_chart(kind, path, title="", subtitle="", source="", theme=None, x=None, y=None, group=None,
                 size=None, label=None, parent=None, val=None, a=None, b=None, lo=None, hi=None,
                 grid=True, markers=True, highlights=None, unbounded=False):
    """Draw one taxonomy chart. Aliases call flow, arch, seq, or geo. terrain and print refuse."""
    kind = str(kind or "").strip().lower()
    if kind not in _CHART_BLURB:
        raise SystemExit(f"unknown chart type '{kind}'. Run: py graph.py describe")
    if kind == "terrain":
        raise SystemExit("terrain is not drawn. A DEM raster is outside this library. Use contour for a z grid.")
    if kind == "print":
        raise SystemExit("print is not a separate drawing. Use geo, then export --to pdf.")
    t = theme or THEME
    if kind in CHART_ALIAS:
        return _render_alias(kind, path, title, subtitle, source, t, x, y, label, val, grid, markers, highlights)
    if kind == "math" and not str(path).lower().endswith(".json"):
        try:
            spec, rows = _math_from_text(path), []
        except (OSError, ValueError) as exc:
            raise SystemExit(str(exc))
    else:
        spec, rows = _load_input(path)
    if isinstance(spec, dict):
        title = title or spec.get("title") or kind
        subtitle = subtitle or spec.get("sub") or spec.get("subtitle") or ""
    else:
        title = title or kind
    opt = {"title": title, "sub": subtitle, "source": source, "t": t, "x": x, "y": y, "group": group,
           "size": size, "label": label, "parent": parent, "val": val, "a": a, "b": b, "lo": lo, "hi": hi,
           "grid": grid, "markers": markers, "highlights": highlights or [], "unbounded": unbounded, "spec": spec}
    if spec is None and not rows:
        raise SystemExit(f"{path}: no rows")
    return _CHART_FN[kind](spec, rows, opt)


_CSV_NEED = {
    "bubble": ("x", "y", "size"), "beeswarm": ("cat", "val"), "step": ("x", "y"),
    "slope": ("cat", "a", "b"), "bump": ("x", "name", "rank"), "ridgeline": ("group", "val"),
    "stack": ("cat", "group", "val"), "dumbbell": ("cat", "a", "b"), "waterfall": ("cat", "val"),
    "histogram": ("val",), "box": ("group", "val"), "violin": ("group", "val"), "strip": ("group", "val"),
    "pie": ("cat", "val"), "donut": ("cat", "val"), "waffle": ("cat", "val"), "funnel": ("cat", "val"),
    "treemap": ("name", "val"), "icicle": ("name", "val"), "sunburst": ("name", "val"),
    "heatmap": ("x", "y", "val"), "calendar": ("date", "val"), "radar": ("axis", "series", "val"),
    "polar": ("cat", "val"), "candle": ("x", "open", "high", "low", "close"),
    "status": ("row", "col", "state"), "forest": ("cat", "est", "lo", "hi"), "qq": ("val",),
    "volcano": ("x", "y"), "sankey": ("src", "dst", "val"), "stream": ("x", "group", "val"),
    "combo": ("x", "bar", "line"), "quadrant": ("x", "y"), "contour": ("x", "y", "z"),
    "heatgeo": ("lat", "lon", "val"), "od": ("lon", "lat", "lon2", "lat2"), "cluster": ("lat", "lon"),
}
_JSON_NEED = {
    "dag": ("nodes", "edges"), "force": ("nodes", "edges"), "radial": ("nodes",),
    "tree": ("nodes",), "dtree": ("nodes",), "nested": ("nodes",), "kg": ("nodes", "edges"),
    "context": ("nodes",), "uml": ("nodes",), "deploy": ("zones",), "layers": ("layers",),
    "integration": ("nodes",), "current": ("nodes",), "er": ("entities",), "wardley": ("nodes",),
    "swim": ("lanes", "nodes"), "state": ("nodes",), "bpmn": ("nodes",), "fishbone": ("ribs",),
    "flywheel": ("nodes",), "kanban": ("columns",), "gantt": ("tasks",), "timeline": ("events",),
    "journey": ("stages",), "story": ("releases",), "org": ("nodes",), "venn": ("sets",),
    "choropleth": ("features",),
}
_EXPLICIT_ROLE = {"x": "x", "y": "y", "group": "group"}


def _validate_math_spec(spec, errors, warnings):
    try:
        curves = [_math_compile_item(item) for item in _math_items(spec)]
    except ValueError as exc:
        _vissue(errors, warnings, "E", str(exc), "use y=f(x), (x(t), y(t)), or f(x,y)=0")
        return
    if spec.get("budget", True) is not False and len(curves) > 8:
        _vissue(errors, warnings, "E", f"{len(curves)} equations > 8", "split the figure, or set budget false")
    if sum(1 for curve in curves if curve.get("focal")) > 2:
        _vissue(errors, warnings, "E", "focal on >2 equations erases signal", "keep 1-2 focal curves")


def _validate_chart(kind, target, args, errors, warnings):
    if kind in ("terrain", "print"):
        _vissue(errors, warnings, "E", _CHART_BLURB[kind], "pick a type that draws")
        return
    if kind == "math":
        try:
            spec = load_spec(target) if str(target).lower().endswith(".json") else _math_from_text(target)
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError) as exc:
            _vissue(errors, warnings, "E", f"unreadable spec: {exc}", "pass JSON equations or a text file")
            return
        if not isinstance(spec, dict):
            _vissue(errors, warnings, "E", "spec is not an object", "pass a JSON object")
            return
        if getattr(args, "no_budget", False):
            spec = dict(spec, budget=False)
        _validate_math_spec(spec, errors, warnings)
        return
    base = CHART_ALIAS.get(kind)
    if base in ("flow", "arch", "seq"):
        try:
            spec = load_spec(target)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            _vissue(errors, warnings, "E", f"unreadable spec: {exc}", "pass a JSON spec")
            return
        _validate_spec_dict(spec, errors, warnings)
        return
    if base == "geo" or kind in ("heatgeo", "cluster", "od"):
        if not str(target).lower().endswith(".csv") and base == "geo":
            return
    if kind in _JSON_NEED and not str(target).lower().endswith(".csv"):
        try:
            spec = load_spec(target)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            _vissue(errors, warnings, "E", f"unreadable spec: {exc}", "pass JSON")
            return
        if not isinstance(spec, dict):
            _vissue(errors, warnings, "E", "spec is not an object", "pass a JSON object")
            return
        for key in _JSON_NEED[kind]:
            if key not in spec:
                _vissue(errors, warnings, "E", f"missing '{key}'", _CHART_BLURB.get(kind, ""))
        return
    if kind not in _CSV_NEED and kind not in ("heatgeo", "cluster", "od", "point"):
        return
    import csv as _csv
    try:
        with open(target, newline="", encoding="utf-8") as f:
            rd = _csv.DictReader(f)
            cols, body = rd.fieldnames or [], list(rd)
    except FileNotFoundError:
        _vissue(errors, warnings, "E", f"file not found: {target}", "")
        return
    if not cols:
        _vissue(errors, warnings, "E", "no header row", "add a header")
        return
    roles = _CSV_NEED.get(kind, ())
    explicit = {"x": getattr(args, "x", None), "y": getattr(args, "y", None), "group": getattr(args, "group", None)}
    # map a couple of CLI flags onto the roles this type actually uses
    role_flag = {}
    if "x" in roles:
        role_flag["x"] = explicit["x"]
    if "y" in roles:
        role_flag["y"] = explicit["y"]
    if "group" in roles:
        role_flag["group"] = explicit["group"]
    fake = [{c: "" for c in cols}]
    for role in roles:
        if not _col(fake, role_flag.get(role), role):
            _vissue(errors, warnings, "E", f"need a {role} column in {cols}", "rename the header or pass the matching flag")
    if len(body) > 400:
        warnings.append({"msg": f"n={len(body)} rows", "fix": "aggregate, or pass --no-budget at render time"})


_missing_charts = [k for k in _CHART_BLURB if k not in CHART_ALIAS and k not in ("terrain", "print") and k not in _CHART_FN]
if _missing_charts:
    raise RuntimeError("chart types without a renderer: " + ", ".join(_missing_charts))

def write_out(svg, kind, title, sub, eyebrow, out, caption="", cap_title="", source="", corners="editorial", theme=None):
    t = theme or THEME
    # -o NAME.html, NAME.svg, or NAME all give NAME.html + NAME.svg side by side
    base, ext = os.path.splitext(out)
    if ext.lower() not in (".html", ".htm", ".svg"):
        base = out
    out = base + ".html"
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


_RECEIPT_PATHS = ("spec", "csv", "src")


def save_receipt(out, payload):
    """Input paths are stored relative to the receipt, so export works from any directory."""
    base, _ = os.path.splitext(out)
    home = os.path.dirname(os.path.abspath(base))
    for k in _RECEIPT_PATHS:
        if isinstance(payload.get(k), str) and os.path.exists(payload[k]):
            try:
                payload[k] = os.path.relpath(os.path.abspath(payload[k]), home).replace(os.sep, "/")
            except ValueError:  # another drive on Windows
                payload[k] = os.path.abspath(payload[k])
    with open(base + ".graph.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _receipt_inputs(r, rcpt):
    """Resolve receipt input paths: beside the receipt first, then the working directory."""
    home = os.path.dirname(os.path.abspath(rcpt))
    for k in _RECEIPT_PATHS:
        v = r.get(k)
        if isinstance(v, str) and not os.path.isabs(v):
            near = os.path.join(home, v)
            if os.path.exists(near) or not os.path.exists(v):
                r[k] = near
    return r


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
        _raster_svg.why = "no Edge, Chrome, or cairosvg on this machine"
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
    import time
    if os.path.exists(dest_abs):
        os.remove(dest_abs)
    try:
        p = subprocess.run(cmd, timeout=90, capture_output=True, text=True, errors="replace")
    except (subprocess.TimeoutExpired, OSError) as e:
        shutil.rmtree(folder, ignore_errors=True)
        _raster_svg.why = f"{os.path.basename(browser)} did not finish: {e}"
        return None
    # Edge and Chrome on Windows can hand the job to a running browser and exit at once.
    # The file lands a second or two later, so wait for it before the page is deleted.
    last, deadline = -1, time.time() + 30
    while time.time() < deadline:
        size = os.path.getsize(dest_abs) if os.path.isfile(dest_abs) else -1
        if size > 400 and size == last:
            break
        last = size
        time.sleep(0.4)
    shutil.rmtree(folder, ignore_errors=True)
    if os.path.isfile(dest_abs) and os.path.getsize(dest_abs) > 400:
        return "browser"
    tail = ((p.stderr or "") + (p.stdout or "")).strip().splitlines()[-2:]
    _raster_svg.why = (f"{browser} ran (exit {p.returncode}) but wrote no {kind}"
                       + (f": {' / '.join(tail)}" if tail else ""))
    return None


_raster_svg.why = ""


def _svg_model(svg):
    """Boxes, decisions, arrows, and frames of a drawn flow or arch, read back from the data-*
    attributes the renderers write. The editable exports are built from this."""
    import re
    nodes, edges, frames = {}, [], []
    for m in re.finditer(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="([\d.]+)"[^>]*?'
                         r'stroke="([^"]*)"[^>]*data-node="([^"]*)" data-label="([^"]*)"', svg):
        x, y, w, h, rx = (float(m.group(k)) for k in range(1, 6))
        nid = html.unescape(m.group(7))
        nodes[nid] = {"id": nid, "label": html.unescape(m.group(8)), "x": x, "y": y, "w": w, "h": h,
                      "shape": "oval" if rx >= 20 else "rect", "stroke": m.group(6)}
    for m in re.finditer(r'<polygon points="([^"]+)"[^>]*stroke="([^"]*)" data-node="([^"]*)" data-label="([^"]*)"', svg):
        v = [float(p) for p in re.findall(r"-?\d*\.?\d+", m.group(1))]
        xs, ys = v[0::2], v[1::2]
        nid = html.unescape(m.group(3))
        nodes[nid] = {"id": nid, "label": html.unescape(m.group(4)), "x": min(xs), "y": min(ys),
                      "w": max(xs) - min(xs), "h": max(ys) - min(ys), "shape": "diamond", "stroke": m.group(2)}
    for m in re.finditer(r'<path d="([^"]+)" fill="none" stroke="([^"]*)"[^>]*data-from="([^"]*)" '
                         r'data-to="([^"]*)" data-label="([^"]*)"', svg):
        pts = []
        for cmd, a, b, c, d in re.findall(r"([MLQ])\s*([-\d.]+),([-\d.]+)(?:\s+([-\d.]+),([-\d.]+))?", m.group(1)):
            pts.append((float(c), float(d)) if cmd == "Q" and c else (float(a), float(b)))
        edges.append({"from": html.unescape(m.group(3)), "to": html.unescape(m.group(4)), "label": html.unescape(m.group(5)),
                      "dashed": "stroke-dasharray" in m.group(0), "stroke": m.group(2), "points": pts})
    for m in re.finditer(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"[^>]*'
                         r'data-group="([^"]*)" data-name="([^"]*)"', svg):
        x, y, w, h = (float(m.group(k)) for k in range(1, 5))
        frames.append({"id": html.unescape(m.group(5)), "label": html.unescape(m.group(6)), "x": x, "y": y, "w": w, "h": h})
    return {"nodes": list(nodes.values()), "edges": [e for e in edges if e["from"] in nodes and e["to"] in nodes],
            "frames": frames}


def _to_drawio(model, title=""):
    """draw.io (diagrams.net) file: boxes and frames keep their place, arrows keep their bends and stay
    attached to their boxes, so dragging a box drags its arrows."""
    def a(v):
        return html.escape(str(v), quote=True)
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    for k, f in enumerate(model["frames"]):
        cells.append(f'<mxCell id="frame{k}" value="{a(f["label"].upper())}" style="rounded=1;arcSize=6;dashed=1;'
                     f'fillColor=#eeeeee;strokeColor=#888888;verticalAlign=top;align=left;spacingLeft=10;fontSize=10;'
                     f'fontStyle=1;fontColor=#4f5d75;" vertex="1" parent="1"><mxGeometry x="{f["x"]:.0f}" y="{f["y"]:.0f}" '
                     f'width="{f["w"]:.0f}" height="{f["h"]:.0f}" as="geometry"/></mxCell>')
    ids = {}
    for k, n in enumerate(model["nodes"]):
        ids[n["id"]] = f"n{k}"
        shape = {"diamond": "rhombus;", "oval": "rounded=1;arcSize=40;"}.get(n["shape"], "rounded=1;arcSize=8;")
        cells.append(f'<mxCell id="n{k}" value="{a(n["label"])}" style="{shape}whiteSpace=wrap;html=1;fillColor=#ffffff;'
                     f'strokeColor={n["stroke"]};fontStyle=1;" vertex="1" parent="1"><mxGeometry x="{n["x"]:.0f}" '
                     f'y="{n["y"]:.0f}" width="{n["w"]:.0f}" height="{n["h"]:.0f}" as="geometry"/></mxCell>')
    for k, e in enumerate(model["edges"]):
        bends = "".join(f'<mxPoint x="{x:.0f}" y="{y:.0f}"/>' for x, y in e["points"][1:-1])
        style = (f"edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;strokeColor={e['stroke']};"
                 + ("dashed=1;" if e["dashed"] else ""))
        cells.append(f'<mxCell id="e{k}" value="{a(e["label"])}" style="{style}" edge="1" parent="1" '
                     f'source="{ids[e["from"]]}" target="{ids[e["to"]]}"><mxGeometry relative="1" as="geometry">'
                     f'<Array as="points">{bends}</Array></mxGeometry></mxCell>')
    return ('<mxfile host="diagonaldiagrams"><diagram id="d1" name="' + a(title or "Page-1") + '">'
            '<mxGraphModel grid="1" gridSize="10" guides="1" connect="1" arrows="1" page="0"><root>'
            + "".join(cells) + "</root></mxGraphModel></diagram></mxfile>\n")


def _to_excalidraw(model):
    """Excalidraw scene: shapes with their text bound inside, arrows bound to the shapes they join."""
    import random
    rnd = random.Random(7)
    els = []

    def base(eid, kind, x, y, w, h, **kw):
        d = {"id": eid, "type": kind, "x": x, "y": y, "width": w, "height": h, "angle": 0,
             "strokeColor": "#2d3142", "backgroundColor": "transparent", "fillStyle": "solid", "strokeWidth": 1,
             "strokeStyle": "solid", "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
             "roundness": None, "seed": rnd.randint(1, 2 ** 31), "version": 1, "versionNonce": rnd.randint(1, 2 ** 31),
             "isDeleted": False, "boundElements": [], "updated": 1, "link": None, "locked": False}
        d.update(kw)
        return d

    def text(eid, label, cx, cy, size, container=None):
        w = _text_w(label, size)
        return base(eid, "text", cx - w / 2, cy - size * 0.625, w, size * 1.25, text=label, originalText=label,
                    fontSize=size, fontFamily=2, textAlign="center", verticalAlign="middle",
                    containerId=container, lineHeight=1.25)
    for k, f in enumerate(model["frames"]):
        els.append(base(f"frame{k}", "rectangle", f["x"], f["y"], f["w"], f["h"], strokeStyle="dashed",
                        backgroundColor="#eeeeee", strokeColor="#888888", roundness={"type": 3}))
        els.append(text(f"frame{k}t", f["label"].upper(), f["x"] + 12 + _text_w(f["label"].upper(), 12) / 2, f["y"] + 14, 12))
    ids = {}
    for k, n in enumerate(model["nodes"]):
        sid, tid = f"n{k}", f"n{k}t"
        ids[n["id"]] = sid
        kind = {"diamond": "diamond", "oval": "rectangle"}.get(n["shape"], "rectangle")
        rnd_kw = {"roundness": {"type": 3}} if n["shape"] != "diamond" else {}
        shape = base(sid, kind, n["x"], n["y"], n["w"], n["h"], backgroundColor="#ffffff", strokeColor=n["stroke"],
                     boundElements=[{"type": "text", "id": tid}], **rnd_kw)
        els.append(shape)
        els.append(text(tid, n["label"], n["x"] + n["w"] / 2, n["y"] + n["h"] / 2, 16, sid))
    shapes = {e["id"]: e for e in els}
    for k, e in enumerate(model["edges"]):
        aid = f"e{k}"
        x0, y0 = e["points"][0]
        pts = [[x - x0, y - y0] for x, y in e["points"]]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        els.append(base(aid, "arrow", x0, y0, max(xs) - min(xs), max(ys) - min(ys), points=pts,
                        strokeColor=e["stroke"], strokeStyle="dashed" if e["dashed"] else "solid",
                        startBinding={"elementId": ids[e["from"]], "focus": 0, "gap": 2},
                        endBinding={"elementId": ids[e["to"]], "focus": 0, "gap": 2},
                        startArrowhead=None, endArrowhead="arrow", roundness={"type": 2}, elbowed=False,
                        boundElements=[{"type": "text", "id": aid + "t"}] if e["label"] else []))
        shapes[ids[e["from"]]]["boundElements"].append({"type": "arrow", "id": aid})
        shapes[ids[e["to"]]]["boundElements"].append({"type": "arrow", "id": aid})
        if e["label"]:
            mx, my = e["points"][len(e["points"]) // 2]
            els.append(text(aid + "t", e["label"], mx, my, 12, aid))
    return json.dumps({"type": "excalidraw", "version": 2, "source": "diagonaldiagrams", "elements": els,
                       "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None}, "files": {}}, indent=1)


def do_export(args):
    base = args.target
    for ext in (".graph.json", ".html", ".svg"):
        if base.endswith(ext):
            base = base[: -len(ext)]
    rcpt = base + ".graph.json"
    if not os.path.exists(rcpt):
        sys.exit(f"no receipt {rcpt} — re-render with: py graph.py scatter ... -o {base}.html")
    with open(rcpt, encoding="utf-8") as f:
        r = _receipt_inputs(json.load(f), rcpt)
    missing = [r[k] for k in _RECEIPT_PATHS if isinstance(r.get(k), str) and not os.path.exists(r[k])]
    if missing:
        sys.exit(f"export: the input {missing[0]} named in {rcpt} is gone. Render again from the spec.")
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
            svg, _, _ = render_flow(spec, r.get("corners", "editorial"), r.get("auto", False), theme)
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
    elif cmd == "chart":
        svg, _, _, n = render_chart(
            r.get("kind"), r.get("src"), title=r.get("title") or "", subtitle=r.get("subtitle") or "",
            source=r.get("source") or "", theme=theme,
            x=r.get("x"), y=r.get("y"), group=r.get("group"), size=r.get("size"),
            label=r.get("label"), parent=r.get("parent"), val=r.get("val"),
            a=r.get("a"), b=r.get("b"), lo=r.get("lo"), hi=r.get("hi"),
            grid=r.get("grid", True), markers=r.get("markers", True),
            highlights=r.get("highlights") or None, unbounded=r.get("budget") is False)
        unit, dest, note = "items", args.o or f"{base}.{args.to}", " (chart: single layout)"
    else:
        sys.exit(f"unknown receipt cmd '{cmd}'")
    if args.to == "svg":
        with open(dest, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"wrote {dest} ({n} {unit}{note})")
        return
    if args.to in ("drawio", "excalidraw"):
        model = _svg_model(svg)
        if not model["nodes"]:
            sys.exit(f"{args.to} export covers flow and arch diagrams (and Mermaid flowcharts); this figure is a {cmd}")
        with open(dest, "w", encoding="utf-8") as f:
            f.write(_to_drawio(model, r.get("title") or "") if args.to == "drawio" else _to_excalidraw(model))
        print(f"wrote {dest} ({len(model['nodes'])} boxes, {len(model['edges'])} arrows, {len(model['frames'])} frames)")
        return
    how = _raster_svg(svg, dest, args.to, args.width)
    if not how:
        sys.exit(f"{args.to} export failed: {_raster_svg.why}. "
                 "--to svg needs nothing, and the HTML page has an Export PNG button.")
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
    "mermaid": {
        "input": "Mermaid text (.mmd): flowchart/graph, sequenceDiagram, or erDiagram",
        "writes": "py graph.py mermaid DIAGRAM.mmd -o OUT.svg   (flow, seq, or schema; checked and audited like a JSON spec)",
        "flowchart": {
            "nodes": "A[step]  A(step)  A([start or end])  A((start or end))  A{decision?}  A[(store)]",
            "arrows": "A --> B   A -->|label| B   A -- label --> B   A -.-> B (dashed)   A ==> B (focal)   A & B --> C",
            "groups": "subgraph id [Title] ... end",
            "focal": "A:::focal",
            "icons": "fa:fa-user, fa:fa-database, fa:fa-server, fa:fa-cloud ... in a label draw that glyph in the box",
        },
        "sequenceDiagram": "participant A as Name | actor U as User | A->>B: call | B-->>A: reply | A-)B: async event",
        "erDiagram": "A ||--o{ B : verb | A { type name PK }",
        "not drawn": "classDef/style colors, notes, loop/alt blocks, LR direction (flows draw top-down)",
        "example": "flowchart TD\n  A([Push]) --> B{Risky?}\n  B -->|yes| C[Review]\n  B -->|no| D([Ship])\n  C --> D",
    },
    "icons": {"use": 'set "icon" on a flow or arch node', "names": sorted(ICONS)},
    "flow": {
        "input": "JSON spec {title, sub, nodes[], edges[], groups[]}",
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
        "rules": ["blue=HTTP/API, dashed=async, coral=focal", "tech sublabels in mono, names in sans",
                  "a wide layer spreads the canvas so boxes do not overlap",
                  "set budget false to draw past 9 nodes and 12 edges; focal stays at 2"],
        "budgets": {"nodes": 9, "edges": 12, "layers": 6, "over": "one view per C4 level, or budget false"},
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
        "rules": ["non-negative data floors at 0", "Okabe-Ito series colors", "area fill only on a single series"],
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


DESCRIBE.update(_chart_meta())


def do_describe(args):
    print(json.dumps(DESCRIBE[args.type], indent=2) if args.type else json.dumps({"types": sorted(DESCRIBE)}, indent=2))


def _vissue(errors, warnings, code, msg, fix=""):
    (errors if code == "E" else warnings).append({"msg": msg, "fix": fix} if fix else {"msg": msg})


def do_validate(args):
    errors, warnings = _validate_target(args.target, getattr(args, "type", None) or "scatter",
                                        args.x, args.y, args.group, args.facet)
    ok = not errors
    print(json.dumps({"ok": ok, "errors": errors, "warnings": warnings}, indent=2))
    raise SystemExit(0 if ok else 1)


def _validate_target(target, vtype="scatter", x=None, y=None, group=None, facet=None, kind=None, unbounded=False):
    """Every check `validate` runs, as (errors, warnings). Render calls it before drawing."""
    from types import SimpleNamespace
    args = SimpleNamespace(target=target, type=vtype, x=x, y=y, group=group, facet=facet, no_budget=unbounded)
    errors, warnings = [], []
    if vtype in ("terrain", "print"):
        _validate_chart(vtype, target, args, errors, warnings)
        return errors, warnings
    if not os.path.isfile(target):
        return [{"msg": f"no file {target}", "fix": "check the path; write the spec or CSV first"}], []
    if vtype in _CHART_BLURB:
        _validate_chart(vtype, args.target, args, errors, warnings)
        return errors, warnings
    if args.target.endswith(".csv"):
        import csv as _csv
        try:
            with open(args.target, newline="", encoding="utf-8") as f:
                rd = _csv.DictReader(f)
                cols, rows = rd.fieldnames or [], list(rd)
        except (FileNotFoundError, UnicodeDecodeError) as e:
            return [{"msg": f"unreadable CSV {args.target}: {e}", "fix": "save it as UTF-8 with a header row"}], []
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
                    warnings.append({"msg": f"n={len(rows)}: drawn as small dots" + (", 5,000 of them sampled" if len(rows) > 5000 else ""),
                                     "fix": "aggregate or --facet split if the cloud hides the pattern"})
                for c in (args.group, args.facet):
                    if c and c in cols and len({r[c] for r in rows}) > 8:
                        warnings.append({"msg": f"'{c}' has {len({r[c] for r in rows})} distinct values", "fix": "keep top-7 + Other"})
    else:
        try:
            spec = load_spec(args.target)
        except (FileNotFoundError, json.JSONDecodeError, SystemExit, ValueError) as e:
            return [{"msg": f"unreadable spec: {_json_where(e)}", "fix": "strict JSON: double quotes, no trailing commas, no comments"}], []
        if isinstance(spec, dict) and (spec.get("equations") or spec.get("expr")) and "nodes" not in spec and "actors" not in spec:
            _validate_math_spec(spec, errors, warnings)
        else:
            _validate_spec_dict(spec, errors, warnings, kind)
    return errors, warnings


def _json_where(e):
    if isinstance(e, json.JSONDecodeError):
        return f"line {e.lineno} column {e.colno}: {e.msg}"
    return str(e)


def _validate_spec_dict(spec, errors, warnings, kind=None):
    """Shared diagram-spec checks for `validate` + `doc`. Appends E/W dicts."""
    if not _structure_ok(spec, errors, warnings, kind):
        return
    if "actors" in spec or "messages" in spec:
        actors, messages = spec.get("actors", []), spec.get("messages", [])
        a_ids = [a.get("id") for a in actors]
        if len(set(a_ids)) != len(a_ids):
            _vissue(errors, warnings, "E", "duplicate actor ids", "make actor ids unique")
        if len(actors) > 6 and spec.get("budget", True) is not False:
            _vissue(errors, warnings, "E", f"{len(actors)} actors > budget 6", "split into sub-sequences, or set budget false")
        if len(messages) > 16 and spec.get("budget", True) is not False:
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
        if len(tables) > 6 and spec.get("budget", True) is not False:
            _vissue(errors, warnings, "E", f"{len(tables)} tables > budget 6", "split into bounded context views, or set budget false")
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
        if spec.get("budget", True) is not False:
            if len(nodes) > 9:
                _vissue(errors, warnings, "E", f"{len(nodes)} nodes > budget 9", "split into overview + detail views, or set budget false")
            if len(edges) > 12:
                _vissue(errors, warnings, "E", f"{len(edges)} edges > budget 12", "drop obvious-from-layout arrows, or set budget false")
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
    import math
    try:
        return math.isfinite(float(v))
    except (ValueError, TypeError):
        return False


_SPEC_KEYS = {"flow": "nodes", "arch": "nodes", "seq": "actors", "schema": "tables"}


def _structure_ok(spec, errors, warnings, kind=None):
    """The shape every diagram renderer assumes. Run first, so a malformed spec
    gets a sentence and a fix, not a traceback."""
    if not isinstance(spec, dict):
        _vissue(errors, warnings, "E", f"the spec is a JSON {type(spec).__name__}, not an object",
                'wrap it: {"title": "...", "nodes": [...], "edges": [...]}')
        return False
    warnings.extend(spec.get("_warnings") or [])
    if spec.get("_errors"):
        errors.extend(spec["_errors"])
        return False
    have = next((k for k in ("nodes", "actors", "tables") if k in spec), None)
    want = _SPEC_KEYS.get(kind)
    if want and want not in spec:
        other = {"nodes": "flow or arch", "actors": "seq", "tables": "schema"}.get(have)
        _vissue(errors, warnings, "E", f"{kind} needs a '{want}' list" + (f"; this spec has '{have}', which is a {other} spec" if other else ""),
                f"run `describe {kind}` for the shape" + (f", or render it with {other}" if other else ""))
        return False
    lists = {"nodes": ("id", "name"), "edges": ("from", "to"), "actors": ("id",),
             "messages": ("from", "to"), "tables": ("id",), "relations": ("from", "to")}
    ok = True
    for key, need in lists.items():
        if key not in spec:
            continue
        items = spec[key]
        if not isinstance(items, list):
            _vissue(errors, warnings, "E", f"'{key}' is a {type(items).__name__}, not a list", f"make '{key}' a JSON array of objects")
            ok = False
            continue
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                eg = "{" + ", ".join(f'"{k}": "..."' for k in need) + "}"
                _vissue(errors, warnings, "E", f"{key}[{i}] is {json.dumps(it)[:40]}, not an object", f"write it as {eg}")
                ok = False
                break
            miss = [k for k in need if k not in it or it[k] in (None, "")]
            if key in ("nodes", "actors", "tables") and miss == ["name"]:
                continue  # a name falls back to the id
            if miss:
                _vissue(errors, warnings, "E", f"{key}[{i}] has no '{miss[0]}'", f"every item in '{key}' needs {', '.join(need)}")
                ok = False
                break
    for i, n in enumerate(spec.get("nodes") or []):
        if not isinstance(n, dict):
            break
        for k in ("rank", "lane"):
            if k in n and (isinstance(n[k], bool) or not isinstance(n[k], (int, float))):
                _vissue(errors, warnings, "E", f"nodes[{i}] '{n.get('id')}': {k} is {json.dumps(n[k])}, not a number",
                        f"{k} is an integer" + (": -1 left, 0 center, 1 right" if k == "lane" else ": 0 is the top row"))
                ok = False
        if kind == "flow" and n.get("shape") not in (None, "oval", "rect", "diamond", "dot"):
            warnings.append({"msg": f"node '{n.get('id')}' shape '{n.get('shape')}' draws as rect",
                             "fix": "oval | rect | diamond | dot"})
        if kind in ("flow", "arch") and isinstance(n.get("name", ""), str):
            dia = kind == "flow" and n.get("shape") == "diamond"
            need = len(_wrap_px(n.get("name", ""), 100 if dia else 144, 12, True, 99))
            if need > 3:
                warnings.append({"msg": f"node '{n.get('id')}' name needs {need} lines; it is cut to 3",
                                 "fix": "shorten it" + ("; a decision is a short question" if dia else "; put detail in sub")})
        if n.get("icon") and n.get("icon") not in ICONS:
            warnings.append({"msg": f"node '{n.get('id')}' icon '{n.get('icon')}' is not built in; drawn without it",
                             "fix": "one of " + ", ".join(sorted(ICONS))})
        if kind == "flow" and n.get("shape") == "diamond" and n.get("sub"):
            warnings.append({"msg": f"diamond '{n.get('id')}' does not draw its sub",
                             "fix": "put the detail in the step before the decision"})
    return ok


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


_NARROW = set("iljI.,:;'|!()[]{}`ftr ")
_WIDE = set("mwMW@%")


def _text_w(s, fs, bold=False):
    """Width estimate for a system sans. No font metrics in the stdlib, so it errs a little wide."""
    w = 0.0
    for ch in s:
        if ch in _NARROW:
            w += 0.30
        elif ch in _WIDE:
            w += 0.85
        elif ch.isupper():
            w += 0.62
        elif ch.isdigit():
            w += 0.56
        elif ord(ch) > 0x2E80:
            w += 1.0
        else:
            w += 0.52
    return w * fs * (1.06 if bold else 1.0)


def _affine(tf):
    """SVG transform list -> matrix (a, b, c, d, e, f)."""
    import math, re

    def mul(m, n):
        a1, b1, c1, d1, e1, f1 = m
        a2, b2, c2, d2, e2, f2 = n
        return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2, a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
                a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)
    m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for name, raw in re.findall(r"(matrix|translate|scale|rotate)\s*\(([^)]*)\)", tf or ""):
        v = [float(x) for x in re.findall(r"-?\d*\.?\d+(?:e-?\d+)?", raw)]
        if not v:
            continue
        if name == "matrix" and len(v) == 6:
            n = tuple(v)
        elif name == "translate":
            n = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale":
            n = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == "rotate":
            a = math.radians(v[0])
            n = (math.cos(a), math.sin(a), -math.sin(a), math.cos(a), 0, 0)
            if len(v) == 3:
                n = mul(mul((1, 0, 0, 1, v[1], v[2]), n), (1, 0, 0, 1, -v[1], -v[2]))
        else:
            continue
        m = mul(m, n)
    return m


def _xbox(m, x0, y0, x1, y1):
    pts = [(m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]) for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _svg_geometry(root, W, H, stats=None):
    """Collisions an agent cannot see in its own output: label on label, label off the
    canvas, label wider than its box, box on box. Returns error dicts with a fix."""
    import re

    def num(v, d=0.0):
        try:
            return float(str(v).replace("px", "").replace(",", " ").split()[0])
        except (TypeError, ValueError, IndexError):
            return d
    texts, shapes, arrows, seen, z = [], [], [], set(), [0]
    frames, named = [], []  # group frames (data-group) and node boxes (data-node)
    diamonds = []  # (cx, cy, half width, half height): arrows are tested against the real shape
    keep = ("font-size", "font-weight", "text-anchor", "dominant-baseline", "opacity", "visibility", "display", "letter-spacing")
    need = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7}

    def path_pts(d):
        # Absolute and relative commands. A curve keeps only its end point: corners are small.
        toks = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?", d or "")
        pts, cur, start, cmd, i = [], (0.0, 0.0), (0.0, 0.0), None, 0
        while i < len(toks):
            tk = toks[i]
            if tk.isalpha():
                cmd, i = tk, i + 1
                if cmd in "Zz":
                    cur = start
                    pts.append(cur)
                continue
            if cmd is None or cmd in "Zz":
                break
            u, n = cmd.upper(), need[cmd.upper()]
            vals = [float(v) for v in toks[i:i + n]]
            if len(vals) < n:
                break
            i += n
            rel = cmd.islower()
            if u == "H":
                x, y = (cur[0] + vals[0] if rel else vals[0]), cur[1]
            elif u == "V":
                x, y = cur[0], (cur[1] + vals[0] if rel else vals[0])
            else:
                x, y = (cur[0] + vals[-2], cur[1] + vals[-1]) if rel else (vals[-2], vals[-1])
            cur = (x, y)
            if u == "M":
                start = cur
                pts.append(None)
                cmd = "l" if rel else "L"
            pts.append(cur)
        return pts

    def walk(el, st, m):
        tag = str(el.tag).split("}")[-1]
        if tag in ("defs", "marker", "clipPath", "mask", "symbol", "pattern", "title", "desc", "style"):
            return
        st = dict(st, **{k: el.get(k) for k in keep if el.get(k) is not None})
        style = el.get("style") or ""
        for k in keep:
            hit = re.search(rf"(?:^|;)\s*{k}\s*:\s*([^;]+)", style)
            if hit:
                st[k] = hit.group(1).strip()
        if st.get("display") == "none" or st.get("visibility") == "hidden" or num(st.get("opacity", 1), 1) <= 0:
            return
        if el.get("transform"):
            n = _affine(el.get("transform"))
            a1, b1, c1, d1, e1, f1 = m
            a2, b2, c2, d2, e2, f2 = n
            m = (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2, a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
                 a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)
        if tag == "text":
            fs = num(st.get("font-size", 12), 12)
            bold = str(st.get("font-weight", "")) in ("600", "700", "800", "900", "bold")
            cx, cy = num(el.get("x")), num(el.get("y"))
            lines = [[el.text or "", cx, cy]]
            for sp in el:  # each positioned <tspan> is its own line
                if str(sp.tag).split("}")[-1] != "tspan":
                    continue
                moved = any(sp.get(k) is not None for k in ("x", "y", "dy"))
                if sp.get("x") is not None:
                    cx = num(sp.get("x"))
                if sp.get("y") is not None:
                    cy = num(sp.get("y"))
                if sp.get("dy") is not None:
                    dy = str(sp.get("dy"))
                    cy += num(dy.replace("em", "")) * (fs if "em" in dy else 1)
                body = "".join(sp.itertext())
                if moved:
                    lines.append([body, cx, cy])
                else:
                    lines[-1][0] += body
                lines[-1][0] += sp.tail or ""
            anc = st.get("text-anchor", "start")
            db = st.get("dominant-baseline", "")
            for s, x, y in lines:
                s = s.strip()
                if not s:
                    continue
                w = _text_w(s, fs, bold)
                ls = str(st.get("letter-spacing") or "0")
                w += len(s) * num(ls.replace("em", "")) * (fs if "em" in ls else 1)
                x0 = x - w / 2 if anc == "middle" else (x - w if anc == "end" else x)
                if db in ("middle", "central"):
                    y0, y1 = y - fs * 0.5, y + fs * 0.5
                elif db in ("hanging", "text-before-edge"):
                    y0, y1 = y, y + fs
                else:
                    y0, y1 = y - fs * 0.72, y + fs * 0.2
                z[0] += 1
                texts.append({"s": s, "fs": fs, "box": _xbox(m, x0, y0, x0 + w, y1), "nl": "\n" in s, "z": z[0]})
            return
        if tag in ("path", "line", "polyline") and (el.get("marker-end") or el.get("marker-start") or "marker" in style):
            if tag == "path":
                raw = path_pts(el.get("d"))
            elif tag == "line":
                raw = [(num(el.get("x1")), num(el.get("y1"))), (num(el.get("x2")), num(el.get("y2")))]
            else:
                v = [float(p) for p in re.findall(r"-?\d*\.?\d+", el.get("points", ""))]
                raw = list(zip(v[0::2], v[1::2]))
            pts = [None if q is None else (m[0] * q[0] + m[2] * q[1] + m[4], m[1] * q[0] + m[3] * q[1] + m[5]) for q in raw]
            real = [q for q in pts if q is not None]
            if len(real) >= 2:
                z[0] += 1
                arrows.append({"pts": pts, "ends": (real[0], real[-1]), "z": z[0]})
        box = None
        if tag == "rect":
            x, y, w, h = (num(el.get(k)) for k in ("x", "y", "width", "height"))
            box = _xbox(m, x, y, x + w, y + h)
            if el.get("data-group") is not None:
                frames.append((box, el.get("data-group"), set((el.get("data-members") or "").split(","))))
            if el.get("data-node") is not None:
                named.append((box, el.get("data-node")))
        elif tag == "polygon":
            v = [float(p) for p in re.findall(r"-?\d*\.?\d+", el.get("points", ""))]
            if len(v) == 8:  # a diamond: test the rectangle inside it, not its bounding box
                b = _xbox(m, min(v[0::2]), min(v[1::2]), max(v[0::2]), max(v[1::2]))
                cx, cy, qw, qh = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2, (b[2] - b[0]) / 4, (b[3] - b[1]) / 4
                box = (cx - qw, cy - qh, cx + qw, cy + qh)
                if (el.get("fill") or "") != "none" and (cx, cy) not in [(d[0], d[1]) for d in diamonds]:
                    diamonds.append((cx, cy, 2 * qw, 2 * qh))
        if box:
            bw, bh = box[2] - box[0], box[3] - box[1]
            filled = (el.get("fill") or "black") != "none" or el.get("stroke")
            big = W and H and bw * bh > 0.5 * W * H
            key = tuple(round(c, 1) for c in box)
            if filled and bw >= 10 and bh >= 10 and not big and key not in seen:
                seen.add(key)
                z[0] += 1
                shapes.append({"box": box, "tag": tag, "z": z[0]})
        for c in el:
            walk(c, st, m)

    walk(root, {}, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))

    def inter(a, b):
        return max(0.0, min(a[2], b[2]) - max(a[0], b[0])), max(0.0, min(a[3], b[3]) - max(a[1], b[1]))

    def inside(a, b, tol=1.0):
        return a[0] - tol <= b[0] and a[1] - tol <= b[1] and a[2] + tol >= b[2] and a[3] + tol >= b[3]

    def at(b):
        return [round((b[0] + b[2]) / 2), round((b[1] + b[3]) / 2)]

    def near(xs, ys=None, cell=64.0):
        # Candidate pairs from a grid, so a chart with thousands of marks stays fast.
        # With one list, pairs come once (i < j); with two, every (i, j) that may touch.
        lim = max(W, H, 1000.0) + 1000.0

        def cells(b):
            x0, y0 = max(-lim, b[0]), max(-lim, b[1])
            x1, y1 = min(lim, b[2]), min(lim, b[3])
            return [(gx, gy) for gx in range(int(x0 // cell), int(x1 // cell) + 1)
                    for gy in range(int(y0 // cell), int(y1 // cell) + 1)]
        grid = {}
        for j, b in enumerate(xs if ys is None else ys):
            for c in cells(b):
                grid.setdefault(c, []).append(j)
        done = set()
        for i, a in enumerate(xs):
            for c in cells(a):
                for j in grid.get(c, ()):
                    if (ys is None and j <= i) or (i, j) in done:
                        continue
                    done.add((i, j))
                    yield i, j
    issues = []
    if len(texts) > 1500:
        # Past this nobody reads the labels, and pairwise checks would take minutes.
        return [{"code": "dense", "msg": f"{len(texts)} labels on one figure",
                 "fix": "aggregate to top-N + Other, facet, or pass --no-audit", "at": [0, 0]}]
    if len(shapes) > 4000:
        shapes = []
    tb = [t["box"] for t in texts]
    sb = [sh["box"] for sh in shapes]
    for t in texts:
        b = t["box"]
        if t["nl"]:
            issues.append({"code": "newline", "msg": f"label '{t['s'][:30]}' has a line break; SVG draws it on one line",
                           "fix": "split it: name for the headline, sub for the detail", "at": at(b)})
        if W and H and (b[0] < -4 or b[2] > W + 4 or b[1] < -4 or b[3] > H + 4):
            issues.append({"code": "clip", "msg": f"label '{t['s'][:30]}' runs off the canvas",
                           "fix": "shorten it", "at": at(b)})
    for i, j in near(tb):
        if True:
            a, b = texts[i], texts[j]
            if a["s"] == b["s"] and abs(a["box"][0] - b["box"][0]) < 1 and abs(a["box"][1] - b["box"][1]) < 1:
                continue  # a halo drawn under its own label
            iw, ih = inter(a["box"], b["box"])
            short = min(a["box"][2] - a["box"][0], b["box"][2] - b["box"][0])
            if iw > max(3.0, 0.15 * short) and ih > 0.4 * min(a["fs"], b["fs"]):
                issues.append({"code": "collide", "msg": f"labels collide: '{a['s'][:24]}' and '{b['s'][:24]}'",
                               "fix": "shorten one, or move it (rank, lane, --note-at)", "at": at(a["box"])})
    for i, j in near(sb):
        if True:
            a, b = shapes[i]["box"], shapes[j]["box"]
            iw, ih = inter(a, b)
            if iw > 4 and ih > 4 and not inside(a, b) and not inside(b, a):
                issues.append({"code": "overlap", "msg": f"boxes overlap at {at((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))}",
                               "fix": "give them different rank or lane, or fewer items per row", "at": at(a)})
    import math

    def crosses(p, q, b):
        # Liang-Barsky: does segment p-q run more than 2px inside box b?
        dx, dy = q[0] - p[0], q[1] - p[1]
        t0, t1 = 0.0, 1.0
        for pk, qk in ((-dx, p[0] - b[0]), (dx, b[2] - p[0]), (-dy, p[1] - b[1]), (dy, b[3] - p[1])):
            if pk == 0:
                if qk < 0:
                    return False
                continue
            r = qk / pk
            if pk < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
            if t0 > t1:
                return False
        return (t1 - t0) * math.hypot(dx, dy) > 2
    # A group frame holds whole boxes. A node holding only its own tag pill is still a node.
    holders = {i for i, j in near(sb, sb)
               if i != j and inside(sb[i], sb[j]) and not inside(sb[j], sb[i]) and sb[j][3] - sb[j][1] >= 24}

    # A pill behind an arrow label masks the arrow on purpose: a short shape around one line of text.
    holders |= {i for i, j in near(sb, tb)
                if inside(sb[i], tb[j], tol=4) and sb[i][3] - sb[i][1] <= 2.5 * (tb[j][3] - tb[j][1])}
    for ar in arrows:
        segs = [(ar["pts"][k], ar["pts"][k + 1]) for k in range(len(ar["pts"]) - 1)
                if ar["pts"][k] is not None and ar["pts"][k + 1] is not None]
        for i, sh in enumerate(shapes):
            b = sh["box"]
            if i in holders or any(b[0] - 6 <= e[0] <= b[2] + 6 and b[1] - 6 <= e[1] <= b[3] + 6 for e in ar["ends"]):
                continue  # a group frame, or the box this arrow leaves or enters
            core = (b[0] + 3, b[1] + 3, b[2] - 3, b[3] - 3)
            if core[2] > core[0] and core[3] > core[1] and any(crosses(p, q, core) for p, q in segs):
                issues.append({"code": "through", "msg": f"an arrow runs through the box at {at(b)}",
                               "fix": "move one node to another lane or rank so the arrow goes around it", "at": at(b)})
        for cx, cy, hw, hh in diamonds:
            if any(abs(e[0] - cx) <= hw + 6 and abs(e[1] - cy) <= hh + 6 for e in ar["ends"]):
                continue  # the decision this arrow leaves or enters
            hit = False
            for p, q in segs:
                n = max(1, int(math.hypot(q[0] - p[0], q[1] - p[1]) // 4))
                if any(abs(p[0] + (q[0] - p[0]) * k / n - cx) / hw + abs(p[1] + (q[1] - p[1]) * k / n - cy) / hh < 0.9
                       for k in range(n + 1)):
                    hit = True
                    break
            if hit:
                issues.append({"code": "through", "msg": f"an arrow runs through the decision at {[round(cx), round(cy)]}",
                               "fix": "move one node to another lane or rank so the arrow goes around it", "at": [round(cx), round(cy)]})
        for t in texts:
            if t["z"] > ar["z"]:
                continue  # the label is painted over the arrow, on purpose
            b = t["box"]
            h = b[3] - b[1]
            core = (b[0] + 1, b[1] + 0.2 * h, b[2] - 1, b[3] - 0.2 * h)
            if core[2] > core[0] and any(crosses(p, q, core) for p, q in segs):
                issues.append({"code": "strike", "msg": f"an arrow is drawn across the label '{t['s'][:24]}'",
                               "fix": "move the node or the label off the arrow's path", "at": at(b)})
    # Two arrows on one line, or ending within 12px of each other on it, read as one arrow
    # that forks: nobody can tell where each goes.
    runs = []
    for k, ar in enumerate(arrows[:300]):
        p = ar["pts"]
        for a, b in zip(p, p[1:]):
            if a is None or b is None:
                continue
            if abs(a[1] - b[1]) < 0.5 and abs(a[0] - b[0]) > 12:
                runs.append((k, "h", round(a[1], 1), min(a[0], b[0]), max(a[0], b[0])))
            elif abs(a[0] - b[0]) < 0.5 and abs(a[1] - b[1]) > 12:
                runs.append((k, "v", round(a[0], 1), min(a[1], b[1]), max(a[1], b[1])))
    shared = set()
    for i in range(len(runs)):
        for j in range(i + 1, len(runs)):
            ka, da, ca, la, ha = runs[i]
            kb, db, cb, lb, hb = runs[j]
            sa, ea = arrows[ka]["ends"]
            sb, eb = arrows[kb]["ends"]
            joint = math.hypot(sa[0] - sb[0], sa[1] - sb[1]) < 3 or math.hypot(ea[0] - eb[0], ea[1] - eb[1]) < 3
            if ka != kb and not joint and da == db and abs(ca - cb) < 2 and min(ha, hb) - max(la, lb) > -12 and (ka, kb) not in shared:
                shared.add((ka, kb))
                mid = (max(la, lb) + min(ha, hb)) / 2
                where = [round(mid), round(ca)] if da == "h" else [round(ca), round(mid)]
                issues.append({"code": "shared", "msg": f"two arrows run on one line at {where}",
                               "fix": "reorder the row or move one node so the arrows take separate paths", "at": where})
    for t in texts:
        b = t["box"]
        mx, my = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        for cx, cy, hw, hh in diamonds:
            if abs(mx - cx) / hw + abs(my - cy) / hh <= 1:
                continue  # the decision's own question
            # measured with the label's background pill, which is what covers the outline
            corners = [(b[0] - 7, b[1] - 2), (b[2] + 7, b[1] - 2), (b[0] - 7, b[3] + 2), (b[2] + 7, b[3] + 2)]
            if any(abs(x - cx) / hw + abs(y - cy) / hh < 1.0 for x, y in corners):
                issues.append({"code": "collide", "msg": f"label '{t['s'][:24]}' sits on the edge of a decision",
                               "fix": "move the label or the node so the decision shows whole", "at": [round(mx), round(my)]})
    for fb, gid, members in frames:
        for nb, nid in named:
            cx, cy = (nb[0] + nb[2]) / 2, (nb[1] + nb[3]) / 2
            if nid not in members and fb[0] < cx < fb[2] and fb[1] < cy < fb[3]:
                issues.append({"code": "intrude", "msg": f"node '{nid}' sits inside group '{gid}' but is not in it",
                               "fix": "move it to another row or lane, or add it to the group", "at": [round(cx), round(cy)]})
    rects = [s["box"] for s in shapes if s["tag"] == "rect"]
    hosts = {}
    for i, j in near(tb, rects):
        b, r = tb[i], rects[j]
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        if r[0] <= cx <= r[2] and r[1] <= cy <= r[3]:
            if i not in hosts or (r[2] - r[0]) * (r[3] - r[1]) < (hosts[i][2] - hosts[i][0]) * (hosts[i][3] - hosts[i][1]):
                hosts[i] = r
    for i, r in sorted(hosts.items()):
        t, b = texts[i], tb[i]
        if True:
            if b[0] < r[0] + 2 or b[2] > r[2] - 2:  # a label keeps 2px clear of its box edge
                issues.append({"code": "spill", "msg": f"label '{t['s'][:30]}' fills or overflows its box",
                               "fix": "2-4 words for a name; put detail in sub", "at": at(b)})
    if stats is not None:
        # For layout repair: how many arrow segments cross, and how much arrow there is.
        hs = [r for r in runs if r[1] == "h"]
        vs = [r for r in runs if r[1] == "v"]
        stats["crossings"] = sum(1 for kh, _, y, x0, x1 in hs for kv, _, x, y0, y1 in vs
                                 if kh != kv and x0 + 1 < x < x1 - 1 and y0 + 1 < y < y1 - 1)
        stats["wire"] = sum(r[4] - r[3] for r in runs)
    out, dedup = [], set()
    for it in issues:
        k = (it["code"], it["msg"])
        if k not in dedup:
            dedup.add(k)
            out.append(it)
    return out


def do_audit(args):
    rep = _audit_file(args.target)
    print(json.dumps(rep, indent=2))
    raise SystemExit(0 if rep["ok"] else 1)


def _audit_file(p):
    """Every check `audit` runs, as a report dict. Render calls it after drawing."""
    import re, xml.etree.ElementTree as ET
    errors, warnings = [], []
    if not os.path.isfile(p):
        return {"ok": False, "errors": [{"msg": f"no file {p}", "fix": "render first; audit takes the .svg or .html it wrote"}], "warnings": []}
    raw = open(p, encoding="utf-8", errors="replace").read()
    m = re.search(r"<svg[\s\S]*?</svg>", raw)
    svg = m.group(0) if m else raw
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as e:
        return {"ok": False, "errors": [{"msg": f"malformed SVG: {e}"}], "warnings": []}
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
    for it in _svg_geometry(root, W, H):
        (warnings if it["code"] == "newline" else errors).append(it)
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "stats": {"texts": len(texts), "points": circles, "canvas": [W, H]}}


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
    """MCP server over stdio: newline-delimited JSON-RPC, standard library only.
    `render` takes the spec or CSV inline, then validates, draws, and audits in one call.
    Tools return paths and a verdict, never pixels, so a call costs tens of tokens."""
    import subprocess
    import tempfile
    me = os.path.abspath(__file__)
    src = {"spec": {"type": "object", "description": "JSON spec, inline"},
           "data": {"type": "string", "description": "CSV text, inline"},
           "path": {"type": "string", "description": "or a spec/CSV file on disk"}}
    opts = {"type": "object", "description": 'CLI flags without dashes, e.g. {"x": "month", "y": "signups", '
                                             '"group": "product", "title": "...", "highlight": ["Atlas"]}. describe lists them.'}
    TOOLS = [
        {"name": "describe", "description": "The spec shape, flags, and budgets for one figure type. No type: the list of types.",
         "inputSchema": {"type": "object", "properties": {"type": {"type": "string"}}}},
        {"name": "render", "description": "Validate, draw, and audit one figure. Writes OUT.svg, OUT.html, and a receipt. "
                                          "ok false: read errors, change the spec or options, call again.",
         "inputSchema": {"type": "object", "required": ["type", "out"],
                         "properties": dict(type={"type": "string", "description": "mermaid (data = Mermaid text), flow, arch, seq, schema, bar, line, scatter, geo, or any describe type"},
                                            out={"type": "string", "description": "output path ending .html"},
                                            options=opts, **src)}},
        {"name": "validate", "description": "Check a spec or CSV without drawing.",
         "inputSchema": {"type": "object", "required": ["type"],
                         "properties": dict(type={"type": "string"}, options=opts, **src)}},
        {"name": "audit", "description": "Check any SVG for collisions, clipping, and arrows through boxes.",
         "inputSchema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}}},
        {"name": "export", "description": "Write png, pdf, or svg from a rendered figure's receipt.",
         "inputSchema": {"type": "object", "required": ["path"],
                         "properties": {"path": {"type": "string"}, "to": {"type": "string", "enum": ["png", "pdf", "svg"]},
                                        "layout": {"type": "string"}, "out": {"type": "string"}}}},
        {"name": "infer", "description": "Propose a scatter spec from a CSV.",
         "inputSchema": {"type": "object", "properties": {"data": {"type": "string"}, "path": {"type": "string"}}}},
    ]
    diagrams = set(_SPEC_KEYS)
    own = {"bar", "line", "scatter", "geo"}

    def flags(o):
        out = []
        for k, v in (o or {}).items():
            flag = "--" + str(k).lstrip("-").replace("_", "-")
            if v is True:
                out.append(flag)
            elif v is False:
                if k in ("grid", "markers"):
                    out.append("--no-" + k)
            elif isinstance(v, list):
                for item in v:
                    out += [flag, str(item)]
            elif v is not None:
                out += [flag, str(v)]
        return out

    def source(a, out_path=None):
        """The input as a file. Inline input is written beside the output, so export can redraw it."""
        if a.get("path") or a.get("target"):
            return a.get("path") or a.get("target")
        if a.get("spec") is not None:
            body, ext = json.dumps(a["spec"], indent=1), ".json"
        elif a.get("data") is not None:
            body = str(a["data"])
            if a.get("type") == "mermaid" or _mermaid_kind(body):
                ext = ".mmd"
            else:
                ext = ".geojson" if body.lstrip().startswith("{") else ".csv"
        else:
            raise ValueError("pass spec (JSON object), data (CSV text), or path")
        if out_path:
            dest = os.path.splitext(out_path)[0] + ".input" + ext
            os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        else:
            fd, dest = tempfile.mkstemp(prefix="diagonaldiagrams-", suffix=ext)
            os.close(fd)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(body)
        return dest

    def command(name, a):
        kind = str(a.get("type") or "")
        if name == "describe":
            return ["describe"] + ([kind] if kind else [])
        if name == "audit":
            return ["audit", a.get("path") or a.get("target")]
        if name == "infer":
            return ["infer", source(a)]
        if name == "export":
            c = ["export", a.get("path") or a.get("target"), "--to", a.get("to") or "png"]
            if a.get("layout"):
                c += ["--layout", a["layout"]]
            return c + (["-o", a["out"]] if a.get("out") else [])
        if name == "validate":
            o = dict(a.get("options") or {})
            target = source(a)
            if kind in own or kind in _CHART_BLURB:
                # validate reads the CSV columns from --x/--y; map the bar names onto them
                o.setdefault("x", o.pop("cat", None) or o.get("x"))
                o.setdefault("y", o.pop("val", None) or o.get("y"))
                o = {k: v for k, v in o.items() if k in ("x", "y", "group", "facet") and v}
                return ["validate", target, "--type", kind] + flags(o)
            return ["validate", target]
        if name == "render":
            if not kind:
                raise ValueError("render needs type")
            out = a.get("out") or ""
            if not out.endswith(".html"):
                out = os.path.splitext(out)[0] + ".html" if out else "diagonaldiagrams-out.html"
            target = source(a, out)
            head = [kind] if (kind in diagrams or kind in own or kind == "mermaid") else ["chart", kind]
            return head + [target, "-o", out] + flags(a.get("options"))
        raise ValueError(f"unknown tool {name}")

    def call(name, a):
        try:
            argv = command(name, a or {})
        except (ValueError, KeyError, TypeError) as e:
            return {"isError": True, "content": [{"type": "text", "text": json.dumps({"ok": False, "errors": [{"msg": str(e)}]})}]}
        if any(x is None for x in argv):
            return {"isError": True, "content": [{"type": "text", "text": f"{name}: a required argument is missing"}]}
        try:
            p = subprocess.run([sys.executable, me] + argv, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=180)
        except subprocess.TimeoutExpired:
            return {"isError": True, "content": [{"type": "text", "text": f"{name} took over 180 s"}]}
        text = ((p.stdout or "") + (p.stderr or "")).strip()
        return {"content": [{"type": "text", "text": text[:12000]}], **({"isError": True} if p.returncode else {})}

    known = ("2025-06-18", "2025-03-26", "2024-11-05")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        if not isinstance(m, dict) or "id" not in m:
            continue  # a notification: never answered
        mid, method, params = m.get("id"), m.get("method"), m.get("params") or {}
        reply = {"jsonrpc": "2.0", "id": mid}
        if method == "initialize":
            want = params.get("protocolVersion")
            reply["result"] = {"protocolVersion": want if want in known else known[0],
                               "capabilities": {"tools": {}},
                               "serverInfo": {"name": "diagonaldiagrams", "version": __version__}}
        elif method == "ping":
            reply["result"] = {}
        elif method == "tools/list":
            reply["result"] = {"tools": TOOLS}
        elif method == "tools/call":
            reply["result"] = call(params.get("name"), params.get("arguments"))
        else:
            reply["error"] = {"code": -32601, "message": f"method not found: {method}"}
        sys.stdout.write(json.dumps(reply) + "\n")
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


def _report(obj, code):
    print(json.dumps(obj))
    raise SystemExit(code)


def _prevalidate(a):
    """Render runs validate first. A bad spec stops here with the same JSON validate prints."""
    if a.cmd in _SPEC_KEYS:
        errors, warnings = _validate_target(a.spec, "spec", kind=a.cmd)
    elif a.cmd == "bar":
        errors, warnings = _validate_target(a.csv, "bar", a.cat, a.val)
    elif a.cmd == "line":
        errors, warnings = _validate_target(a.csv, "line", a.x, a.y, a.group)
    elif a.cmd == "scatter":
        errors, warnings = _validate_target(a.csv, "scatter", a.x, a.y, a.group, a.facet)
    elif a.cmd == "geo":
        errors, warnings = _validate_target(a.src, "geo", a.lon, a.lat)
    elif a.cmd == "chart" and a.kind in _CHART_BLURB:
        errors, warnings = _validate_target(a.src, a.kind, a.x, a.y, a.group, unbounded=a.no_budget)
    else:
        return []
    if errors:
        _report({"ok": False, "stage": "validate", "errors": errors, "warnings": warnings,
                 "next": "fix the spec or flags and run the same command again; nothing was drawn"}, 1)
    return warnings


def _outline(svg_path):
    """The drawn layout as text: each row's boxes left to right, and each frame's members. Lets an
    agent check the structure for a few dozen tokens instead of looking at a picture."""
    import re
    try:
        raw = open(svg_path, encoding="utf-8").read()
    except OSError:
        return None
    boxes, label = [], {}
    for m in re.finditer(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"[^>]*data-node="([^"]*)" data-label="([^"]*)"', raw):
        x, y, w, h = (float(m.group(k)) for k in range(1, 5))
        label[html.unescape(m.group(5))] = html.unescape(m.group(6))
        boxes.append((y + h / 2, x + w / 2, html.unescape(m.group(6))))
    for m in re.finditer(r'data-node="([^"]*)" data-label="([^"]*)" data-cx="([-\d.]+)" data-cy="([-\d.]+)"', raw):
        label[html.unescape(m.group(1))] = html.unescape(m.group(2))
        boxes.append((float(m.group(4)), float(m.group(3)), html.unescape(m.group(2)) + " (decision)"))
    if not boxes:
        return None
    rows = []
    for cy, cx, name in sorted(boxes):
        if rows and abs(rows[-1][0] - cy) < 30:
            rows[-1][1].append((cx, name))
        else:
            rows.append([cy, [(cx, name)]])
    out = [f"row {k + 1}: " + " | ".join(n for _, n in sorted(r[1])) for k, r in enumerate(rows)]
    for m in re.finditer(r'data-group="[^"]*" data-name="([^"]*)" data-members="([^"]*)"', raw):
        names = [label.get(html.unescape(v), html.unescape(v)) for v in m.group(2).split(",") if v]
        out.append(f"frame {html.unescape(m.group(1))}: " + ", ".join(names))
    return out


def _finish(a, html, svg, count, unit, pre):
    """One JSON line per render: the files, the count, and the audit verdict."""
    rep = {"ok": True, "errors": [], "warnings": []} if getattr(a, "no_audit", False) else _audit_file(svg)
    out = {"ok": rep["ok"], "svg": svg, "html": html, "receipt": os.path.splitext(html)[0] + ".graph.json", unit: count}
    layout = _outline(svg)
    if layout:
        out["layout"] = layout
    if rep["errors"]:
        out["errors"] = rep["errors"]
        out["next"] = ("the files are written so you can look; change the spec or flags and render again "
                       "(--no-audit accepts the figure as it is)")
    warns = list(pre or []) + rep["warnings"]
    if warns:
        out["warnings"] = warns
    _report(out, 0 if rep["ok"] else 1)


def _chart_flags(p):
    p.add_argument("--grid", dest="grid", action="store_true", help="draw gridlines (default)")
    p.add_argument("--no-grid", dest="grid", action="store_false", help="drop gridlines; keep ticks")
    p.add_argument("--markers", dest="markers", action="store_true", help="point dots or bar value labels (default)")
    p.add_argument("--no-markers", dest="markers", action="store_false", help="hide point dots or bar value labels")
    p.add_argument("--highlight", action="append", default=[],
                   help="category, x value, group, or place drawn in accent (repeatable)")
    p.add_argument("--no-audit", action="store_true", help="skip the layout check after drawing")
    p.set_defaults(grid=True, markers=True)


def main():
    ap = argparse.ArgumentParser(prog="diagonaldiagrams")
    ap.add_argument("--version", action="version", version=f"diagonaldiagrams {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    _render_parsers = {}
    for name in ("flow", "arch", "seq", "schema", "mermaid"):
        p = sub.add_parser(name); p.add_argument("spec"); p.add_argument("-o", required=True)
        p.add_argument("--corners", default="editorial", choices=["sharp", "rounded", "editorial"])
        p.add_argument("--theme", default="editorial", choices=sorted(THEMES))
        p.add_argument("--theme-file", default=None, help="JSON with theme key overrides")
        p.add_argument("--no-audit", action="store_true", help="skip the layout check after drawing")
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
    p = sub.add_parser("chart", help="draw one taxonomy type: py graph.py chart KIND SRC -o OUT.html")
    p.add_argument("kind")
    p.add_argument("src")
    p.add_argument("-o", required=True)
    p.add_argument("--title", default="")
    p.add_argument("--subtitle", default="")
    p.add_argument("--source", default="")
    p.add_argument("--x", default=None)
    p.add_argument("--y", default=None)
    p.add_argument("--group", default=None)
    p.add_argument("--size", default=None)
    p.add_argument("--label", default=None)
    p.add_argument("--parent", default=None)
    p.add_argument("--val", default=None)
    p.add_argument("--a", default=None)
    p.add_argument("--b", default=None)
    p.add_argument("--lo", default=None)
    p.add_argument("--hi", default=None)
    p.add_argument("--theme", default="editorial", choices=sorted(THEMES))
    p.add_argument("--theme-file", default=None)
    p.add_argument("--no-budget", action="store_true", help="lift the count cap for this figure")
    _chart_flags(p)
    p = sub.add_parser("export", help="render receipt to png/pdf/svg in a layout")
    p.add_argument("target", help="base path, .html or .svg (receipt .graph.json must sit beside it)")
    p.add_argument("--to", default="png", choices=["png", "pdf", "svg", "drawio", "excalidraw"])
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
    _vtypes = sorted(set(["scatter", "bar", "line", "geo"]) | set(_CHART_BLURB))
    p.add_argument("--type", default="scatter", choices=_vtypes,
                   help="shape to check. A chart type uses the same name as chart KIND")
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
    if a.cmd == "mermaid":
        # the text says which diagram it is: flowchart/graph -> flow, sequenceDiagram -> seq, erDiagram -> schema
        try:
            kind = _mermaid_kind(open(a.spec, encoding="utf-8").read())
        except OSError:
            kind = "flow"
        if kind not in ("flow", "seq", "schema"):
            _report({"ok": False, "stage": "validate", "errors": [{
                "msg": f"Mermaid '{kind}' is not read yet" if kind else "this file does not start with a Mermaid diagram type",
                "fix": "start with flowchart TD, graph TD, sequenceDiagram, or erDiagram"}]}, 1)
        a.cmd = kind
    pre = _prevalidate(a)
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
        save_receipt(o, {"cmd": a.cmd, "spec": a.spec, "corners": a.corners, "theme": theme.get("_name"),
                          "auto": bool(getattr(a, "auto", False))})
        _finish(a, o, s, item_cnt, "items", pre)
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
        _finish(a, o, s, n, "bars", pre)
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
                         "xlabel": a.xlabel, "xunit": a.xunit, "ylabel": a.ylabel, "yunit": a.yunit,
                         "source": a.source, "corners": a.corners, "theme": theme.get("_name"),
                         "grid": a.grid, "markers": a.markers, "highlights": a.highlight})
        _finish(a, o, s, n, "points", pre)
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
        _finish(a, o, s, n, "places", pre)
    elif a.cmd == "chart":
        theme = _cli_theme(a)
        svg, _, _, n = render_chart(
            a.kind, a.src, title=a.title, subtitle=a.subtitle, source=a.source, theme=theme,
            x=a.x, y=a.y, group=a.group, size=a.size, label=a.label, parent=a.parent,
            val=a.val, a=a.a, b=a.b, lo=a.lo, hi=a.hi,
            grid=a.grid, markers=a.markers, highlights=a.highlight, unbounded=a.no_budget)
        shown = a.title or a.kind
        o, s = write_out(svg, "chart", shown, a.subtitle or a.kind,
                         f"chart · {a.kind}", a.o,
                         caption=a.subtitle or a.kind, cap_title=shown + ".",
                         source=(a.source or os.path.basename(a.src)), theme=theme)
        save_receipt(o, {"cmd": "chart", "kind": a.kind, "src": a.src, "title": a.title,
                         "subtitle": a.subtitle, "source": a.source,
                         "x": a.x, "y": a.y, "group": a.group, "size": a.size,
                         "label": a.label, "parent": a.parent, "val": a.val,
                         "a": a.a, "b": a.b, "lo": a.lo, "hi": a.hi,
                         "theme": theme.get("_name"), "grid": a.grid, "markers": a.markers,
                         "highlights": a.highlight, "budget": False if a.no_budget else True})
        _finish(a, o, s, n, "items", pre)
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
        _finish(a, o, s, n, "points", pre)


def cli():
    """Entry point. An input the engine does not expect comes back as JSON with a fix, not a traceback."""
    try:
        main()
    except (SystemExit, KeyboardInterrupt):
        raise
    except json.JSONDecodeError as e:
        _report({"ok": False, "errors": [{"msg": f"bad JSON at {_json_where(e)}",
                                          "fix": "strict JSON: double quotes, no trailing commas, no comments"}]}, 1)
    except FileNotFoundError as e:
        _report({"ok": False, "errors": [{"msg": f"no file {e.filename}", "fix": "check the path"}]}, 1)
    except Exception as e:
        import traceback
        where = traceback.extract_tb(e.__traceback__)[-1]
        _report({"ok": False, "errors": [{
            "msg": f"diagonaldiagrams could not draw this input ({type(e).__name__}: {e}, graph.py line {where.lineno})",
            "fix": "run validate on the spec first; if it passes, this is a diagonaldiagrams bug worth reporting with the spec"}]}, 2)


if __name__ == "__main__":
    cli()
