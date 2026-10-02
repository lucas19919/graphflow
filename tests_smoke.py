#!/usr/bin/env python3
"""Active smoke suite for the graph engine. Pure stdlib.
Run:  py tests_smoke.py   (exit 0 = all green, exit 1 = failures listed)
Renders into the system temp dir; the workspace is never polluted.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GRAPH = os.path.join(HERE, "graph.py")
WORK = os.path.join(tempfile.gettempdir(), "graph_smoke")
PASS, FAIL = [], []


def run(*cmd, expect=0):
    p = subprocess.run([sys.executable, GRAPH, *cmd], capture_output=True, text=True, cwd=HERE)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))


def mcp(messages):
    p = subprocess.run([sys.executable, GRAPH, "mcp"], input="\n".join(messages),
                       capture_output=True, text=True, cwd=HERE)
    return [json.loads(l) for l in p.stdout.splitlines() if l.strip()]


def main():
    os.makedirs(WORK, exist_ok=True)
    print("== cli ==")
    rc, _ = run("--help")
    check("help exits 0", rc == 0)
    for t in ("scatter", "flow", "arch", "seq", "schema", "bar", "line", "geo", "export"):
        rc, _ = run("describe", t)
        check(f"describe {t}", rc == 0)

    print("== validate ==")
    rc, _ = run("validate", "examples/flow_decision.json")
    check("validate good flow", rc == 0)
    rc, _ = run("validate", "examples/bad.json")
    check("validate bad flow exits 1", rc == 1)
    rc, _ = run("validate", "examples/seq_checkout.json")
    check("validate good seq", rc == 0)
    rc, _ = run("validate", "examples/schema_ecommerce.json")
    check("validate good schema", rc == 0)
    rc, _ = run("validate", "examples/line_throughput.csv", "--type", "line", "--x", "timestamp", "--y", "rps")
    check("validate line csv", rc == 0)
    rc, _ = run("validate", "examples/bar_latency.csv", "--type", "bar", "--x", "service", "--y", "p99_latency_ms")
    check("validate bar csv", rc == 0)
    rc, out = run("infer", "examples/scatter_groups.csv")
    check("infer proposes spec", rc == 0 and '"group": "tissue"' in out, out[:120])

    print("== render + audit ==")
    jobs = [
        ("scatter", ["examples/scatter_groups.csv", "--x", "dose", "--y", "expr", "--yerr", "expr_err",
                     "--group", "tissue", "--facet", "cohort", "--xlabel", "Dose", "--xunit", "mg",
                     "--ylabel", "Expression", "--yunit", "log2", "-o", f"{WORK}/s.html"]),
        ("flow", ["examples/flow_decision.json", "--corners", "sharp", "-o", f"{WORK}/f.html"]),
        ("arch", ["examples/arch.json", "-o", f"{WORK}/a.html"]),
        ("seq", ["examples/seq_checkout.json", "-o", f"{WORK}/q.html"]),
        ("schema", ["examples/schema_ecommerce.json", "-o", f"{WORK}/d.html"]),
        ("bar", ["examples/bar_latency.csv", "--cat", "service", "--val", "p99_latency_ms",
                 "--unit", "ms", "--sort", "desc", "-o", f"{WORK}/b.html"]),
        ("line", ["examples/line_throughput.csv", "--x", "timestamp", "--y", "rps",
                  "--group", "service", "-o", f"{WORK}/l.html"]),
    ]
    for cmd, args in jobs:
        rc, out = run(cmd, *args)
        base = args[-1].rsplit(".", 1)[0]
        ok = rc == 0 and os.path.exists(base + ".svg")
        check(f"render {cmd}", ok, out[:200])
        if ok:
            rc2, out2 = run("audit", base + ".svg")
            check(f"audit {cmd} clean", rc2 == 0, out2[:200])

    print("== geometry ==")
    import re as _re
    import xml.etree.ElementTree as _ET
    def _els(root, name):
        return [el for el in root.iter() if el.tag.split("}")[-1] == name]
    bar_svg = open(f"{WORK}/b.svg", encoding="utf-8").read()
    broot = _ET.fromstring(bar_svg)
    spines = [el for el in _els(broot, "line") if el.get("stroke-width") == "1.2" and el.get("x1") == el.get("x2")]
    top = min(float(el.get("y1")) for el in spines)
    bars = [el for el in _els(broot, "path") if el.get("d")]
    def _ys(d):
        return [float(y) for y in _re.findall(r"[MLQ]\s*[\d.]+,([\d.]+)", d)]
    def _qs(d):
        return [float(y) for y in _re.findall(r"Q[\d.]+,([\d.]+)", d)]
    check("bar has square-bottom paths", len(bars) >= 5 and all(_qs(el.get("d")) for el in bars))
    check("bar stays inside the plot", all(min(_ys(el.get("d"))) >= top - 0.6 for el in bars),
          f"top={top}")
    # tallest bar is the first when sorted desc; its rounded caps sit above the baseline
    base_line = [el for el in _els(broot, "line") if el.get("stroke-width") == "1.2" and el.get("y1") == el.get("y2")]
    baseline = float(base_line[0].get("y1")) if base_line else None
    check("bar bottoms sit on the axis",
          baseline is not None and all(abs(max(_ys(el.get("d"))) - baseline) < 1.2 for el in bars),
          f"baseline={baseline}")
    check("bar caps are the free end",
          baseline is not None and all(max(_qs(el.get("d"))) < baseline - 4 for el in bars))
    flow_svg = open(f"{WORK}/f.svg", encoding="utf-8").read()
    check("flow title is on the figure", 'font-size="18"' in flow_svg and ">Deploy approval<" in flow_svg)
    froot = _ET.fromstring(flow_svg)
    diamonds = []
    for poly in _els(froot, "polygon"):
        raw = [p.split(",") for p in poly.get("points", "").split() if "," in p]
        pts = [(float(x), float(y)) for x, y in raw if len(x) and len(y)]
        if len(pts) == 4:
            diamonds.append(pts)
    check("flow has a diamond", len(diamonds) >= 1)
    if diamonds:
        pts = diamonds[0]
        cx = sum(p[0] for p in pts) / 4
        cy = sum(p[1] for p in pts) / 4
        hw = max(p[0] for p in pts) - cx
        hh = max(p[1] for p in pts) - cy
        right = max(pts, key=lambda p: p[0])
        starts = [(float(x), float(y)) for x, y in _re.findall(r"M\s*([\d.]+),([\d.]+)", flow_svg)]
        def _inside(x, y):
            return abs(x - cx) / hw + abs(y - cy) / hh < 0.92
        check("flow arrow leaves the diamond's right point",
              any(abs(x - right[0]) < 1.5 and abs(y - right[1]) < 1.5 for x, y in starts),
              str(right))
        check("flow arrows do not start inside the diamond",
              not any(_inside(x, y) for x, y in starts))
    def _terminals(svg):
        pts = []
        for d in _re.findall(r'\bd="([^"]+)"', svg):
            nums = _re.findall(r"([\d.]+),([\d.]+)", d)
            if len(nums) >= 2:
                pts.append((float(nums[0][0]), float(nums[0][1])))
                pts.append((float(nums[-1][0]), float(nums[-1][1])))
        best = 1e9
        for i, a in enumerate(pts):
            for b in pts[i + 1:]:
                best = min(best, ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5)
        return best
    check("flow inputs and outputs do not share a point", _terminals(flow_svg) > 8, f"sep={_terminals(flow_svg):.1f}")
    arch_svg = open(f"{WORK}/a.svg", encoding="utf-8").read()
    horiz = [m for m in _re.finditer(r'M\s*([\d.]+),([\d.]+)\s*L\s*([\d.]+),([\d.]+)', arch_svg)
             if abs(float(m.group(2)) - float(m.group(4))) < 1 and abs(float(m.group(1)) - float(m.group(3))) > 30]
    check("arch sibling arrow leaves sideways", len(horiz) >= 1, f"n={len(horiz)}")
    check("arch inputs do not share a point", _terminals(arch_svg) > 8, f"sep={_terminals(arch_svg):.1f}")
    ink = open(f"{WORK}/ink.svg", encoding="utf-8").read() if False else ""
    rc, _ = run("flow", "examples/flow_decision.json", "--theme", "ink", "-o", f"{WORK}/ink.html")
    ink = open(f"{WORK}/ink.svg", encoding="utf-8").read() if rc == 0 else ""
    check("theme ink reaches the svg", rc == 0 and "#2d3142" in ink)
    html = open(f"{WORK}/b.html", encoding="utf-8").read()
    svg_in_page = html.split("<svg", 1)[-1] if "<svg" in html else ""
    check("html toolbar", 'id="gbar"' in html and "Copy SVG" in html and "Export SVG" in html
          and "Export PNG" in html and "Annotate" not in html and "fonts.googleapis" not in html
          and "<h1" not in html)
    check("title sits inside the copied svg",
          'font-size="18"' in svg_in_page and ">Bar Chart<" in svg_in_page)
    check("print hides the toolbar", "@media print" in html and ".gbar{display:none}" in html)
    rc, _ = run("bar", "examples/bar_latency.csv", "--cat", "service", "--val", "p99_latency_ms",
                "--no-grid", "--no-markers", "--highlight", "Payment Pipeline",
                "--title", "Latency", "--subtitle", "p99", "-o", f"{WORK}/bh.html")
    bh = open(f"{WORK}/bh.svg", encoding="utf-8").read() if rc == 0 else ""
    check("grid and markers are optional",
          rc == 0 and "rgba(45,49,66,0.12)" not in bh and ">340 ms<" not in bh and ">42<" not in bh,
          bh[bh.find("stroke"):bh.find("stroke")+80] if bh else "missing")
    check("highlight and subtitle are on the figure",
          "#eb6c36" in bh and ">Latency<" in bh and ">p99<" in bh)

    print("== geo ==")
    rc, _ = run("validate", "examples/geo_cities.csv", "--type", "geo", "--x", "lon", "--y", "lat")
    check("validate geo", rc == 0)
    rc, _ = run("geo", "examples/geo_cities.csv", "--lat", "lat", "--lon", "lon", "--label", "city",
                "--val", "people_m", "--title", "Cities", "-o", f"{WORK}/g.html")
    check("render geo", rc == 0 and os.path.exists(f"{WORK}/g.svg"))
    if rc == 0:
        rc2, out2 = run("audit", f"{WORK}/g.svg")
        gsvg = open(f"{WORK}/g.svg", encoding="utf-8").read()
        check("audit geo clean", rc2 == 0, out2[:200])
        check("geo draws points and a scale", gsvg.count("<circle") >= 8 and "km" in gsvg)
        check("geo title is on the figure", 'font-size="18"' in gsvg and ">Cities<" in gsvg)
        check("geo draws a coastline", gsvg.count('fill="#f4f0e8"') >= 3)

    print("== flow --auto ==")
    rc, _ = run("flow", "examples/flow_decision.json", "--auto", "-o", f"{WORK}/fa.html")
    check("flow --auto renders", rc == 0 and os.path.exists(f"{WORK}/fa.svg"))
    rc, _ = run("audit", f"{WORK}/fa.svg")
    check("flow --auto audit clean", rc == 0)
    import re as _re
    cross = {"nodes": [{"id": "l", "name": "L", "shape": "oval"}, {"id": "r", "name": "R", "shape": "oval"},
                        {"id": "x", "name": "X"}, {"id": "y", "name": "Y"}],
             "edges": [{"from": "l", "to": "y", "label": "a"}, {"from": "r", "to": "x", "label": "b"}]}
    cj = os.path.join(WORK, "cross.json")
    json.dump(cross, open(cj, "w"))
    rc, _ = run("flow", cj, "--auto", "-o", f"{WORK}/fx.html")
    svgx = open(f"{WORK}/fx.svg").read()
    px = {m.group(2): float(m.group(1)) for m in
          _re.finditer(r'x="([0-9.]+)"[^>]*>([XY])<', svgx)}
    check("flow --auto uncrosses (Y left of X)", rc == 0 and px.get("Y", 1e9) < px.get("X", -1), str(px))

    print("== audit catches slop ==")
    bad_svg = os.path.join(WORK, "bad.svg")
    open(bad_svg, "w").write("<svg viewBox=\"0 0 100 100\"><text font-family='X' font-size=\"24\">DupTitleDupTitleDupTitleDup</text>"
                             "<text font-size=\"24\">DupTitleDupTitleDupTitleDup</text></svg>")
    rc, out = run("audit", bad_svg)
    check("audit rejects slop", rc == 1, out[:160])

    print("== export ==")
    rc, _ = run("export", f"{WORK}/s", "--to", "svg", "--layout", "social", "-o", f"{WORK}/s-social.svg")
    check("export scatter social svg", rc == 0 and os.path.exists(f"{WORK}/s-social.svg"))
    rc, _ = run("export", f"{WORK}/d", "--to", "svg", "-o", f"{WORK}/d-export.svg")
    check("export schema svg", rc == 0 and os.path.exists(f"{WORK}/d-export.svg"))
    rc, out = run("export", f"{WORK}/b", "--to", "png", "-o", f"{WORK}/b.png")
    png = open(f"{WORK}/b.png", "rb").read(8) if rc == 0 and os.path.exists(f"{WORK}/b.png") else b""
    check("export png", rc == 0 and png.startswith(b"\x89PNG") and os.path.getsize(f"{WORK}/b.png") > 1000, out[:220])

    print("== doc ==")
    md = os.path.join(WORK, "t.md")
    open(md, "w").write('# T\n\n```graph:flow id="d1" title="D"\n'
                         '{"nodes": [{"id": "a", "shape": "oval", "name": "A"}], "edges": []}\n```\n')
    rc, _ = run("doc", md, "--out-dir", f"{WORK}/assets")
    check("doc compiles", rc == 0 and os.path.exists(f"{WORK}/assets/d1.svg"))
    rc, _ = run("doc", md, "--out-dir", f"{WORK}/assets")
    anchors = open(md).read().count("<!-- graph:d1 -->")
    check("doc idempotent links", rc == 0 and anchors == 1, f"anchors={anchors}")
    rc, _ = run("doc", md, "--out-dir", f"{WORK}/assets", "--check")
    check("doc --check ok", rc == 0)
    txt = open(md).read().replace('"name": "A"', '"name": "A2"')
    open(md, "w").write(txt)
    rc, _ = run("doc", md, "--out-dir", f"{WORK}/assets", "--check")
    check("doc --check stale exits 1", rc == 1)

    print("== extract + monitor ==")
    sql = os.path.join(WORK, "s.sql")
    open(sql, "w").write("CREATE TABLE t (id UUID PRIMARY KEY, x INT,\nFOREIGN KEY (x) REFERENCES u (id)\n);\n"
                         "CREATE TABLE u (id UUID PRIMARY KEY);\n")
    rc, out = run("extract", "schema", sql)
    spec = json.loads(out)
    fk = [c for t in spec["tables"] for c in t["columns"] if c.get("fk")]
    check("extract marks fk", rc == 0 and len(fk) == 1 and spec["relations"], out[:160])
    prisma = os.path.join(WORK, "m.prisma")
    open(prisma, "w").write("model User {\n  id String @id\n  teamId String?\n"
                            "  team Team? @relation(fields: [teamId], references: [id])\n}\n"
                            "model Team {\n  id String @id\n}\n")
    rc, out = run("extract", "schema", prisma)
    check("extract prisma relations", rc == 0 and "teamId" in out and '"1:N"' in out, out[:160])
    dj = os.path.join(WORK, "m_dj.py")
    open(dj, "w").write("from django.db import models\nclass Team(models.Model):\n"
                        "    name = models.CharField(max_length=9)\n"
                        "class User(models.Model):\n    team = models.ForeignKey(Team, on_delete=models.CASCADE)\n")
    rc, out = run("extract", "schema", dj)
    check("extract django relations", rc == 0 and '"1:N"' in out, out[:160])
    rc, out = run("monitor")
    check("monitor graceful json", rc == 0 and json.loads(out).get("drift") in (True, False), out[:120])

    print("== mcp ==")
    try:
        rs = mcp(['{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}',
                  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"validate","arguments":{"target":"examples/flow_decision.json"}}}'])
        names = [t["name"] for t in rs[0]["result"]["tools"]]
        check("mcp tools/list", "validate" in names and "diagram" in names, str(names))
        check("mcp validate call", '"ok": true' in rs[1]["result"]["content"][0]["text"])
    except Exception as e:  # noqa: BLE001
        check("mcp smoke", False, str(e))

    print("== sync bot (needs git) ==")
    import shutil as _sh
    if _sh.which("git"):
        gp = os.path.join(WORK, "gitproj")
        os.makedirs(gp + "/models", exist_ok=True)
        open(gp + "/models/s.sql", "w").write("CREATE TABLE t (id UUID PRIMARY KEY);\n")
        open(gp + "/graph.monitor.json", "w").write(
            '{"mappings": [{"code": "models/*.sql", "domain": "database", "kind": "schema", "spec": "docs/s.graph.json"}]}')
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", EMAIL="t@t")
        subprocess.run(["git", "init", "-q", gp], check=True)
        subprocess.run(["git", "-C", gp, "add", "-A"], check=True)
        subprocess.run(["git", "-C", gp, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "b"], check=True)
        # v1 spec matches v1 code: extract + commit
        run("extract", "schema", gp + "/models/s.sql", "-o", gp + "/docs/s.graph.json")
        subprocess.run(["git", "-C", gp, "add", "-A"], check=True)
        subprocess.run(["git", "-C", gp, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "s"], check=True)
        open(gp + "/models/s.sql", "w").write("CREATE TABLE t (id UUID PRIMARY KEY, x INT);\n")
        rc, out = run("sync", "--path", gp, "--map", gp + "/graph.monitor.json", "--commit")
        try:
            rep = json.loads(out)
            check("sync fixes drift+commits",
                  rc == 0 and rep["synced"] and rep["committed"]
                  and "+column 'x'" in rep["synced"][0]["diff"], out[:300])
        except (json.JSONDecodeError, KeyError, IndexError):
            check("sync fixes drift+commits", False, out[:300])
        rc, out = run("monitor", "--path", gp, "--map", gp + "/graph.monitor.json", "--ci")
        check("monitor clean after sync", rc == 0 and json.loads(out)["drift"] is False, out[:200])
    else:
        check("sync bot (git absent, skipped)", True)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f": {FAIL}" if FAIL else ""))
    raise SystemExit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
