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
        # an arrow's start and another arrow's end never share a point; arrows that merge into
        # one entry (or split from one exit) may share theirs on purpose
        starts, ends = [], []
        for d in _re.findall(r'\bd="([^"]+)"', svg):
            nums = _re.findall(r"([\d.]+),([\d.]+)", d)
            if len(nums) >= 2:
                starts.append((float(nums[0][0]), float(nums[0][1])))
                ends.append((float(nums[-1][0]), float(nums[-1][1])))
        best = 1e9
        for a in starts:
            for b in ends:
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

    print("== budget ==")
    big = os.path.join(WORK, "big.json")
    nodes = [{"id": f"n{i}", "name": f"N{i}", "layer": i // 4} for i in range(10)]
    edges = [{"from": f"n{i}", "to": f"n{i+1}"} for i in range(9)]
    with open(big, "w", encoding="utf-8") as f:
        json.dump({"title": "Big", "nodes": nodes, "edges": edges}, f)
    rc, _ = run("validate", big)
    check("ten nodes still refused", rc == 1)
    with open(big, encoding="utf-8") as f:
        spec = json.load(f)
    spec["budget"] = False
    with open(big, "w", encoding="utf-8") as f:
        json.dump(spec, f)
    rc, out = run("validate", big)
    check("budget false allows ten nodes", rc == 0, out[:160])

    print("== mcp ==")
    try:
        rs = mcp(['{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}',
                  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"validate","arguments":{"target":"examples/flow_decision.json"}}}'])
        names = [t["name"] for t in rs[0]["result"]["tools"]]
        check("mcp tools/list", "validate" in names and "render" in names, str(names))
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

    charts()
    agent_loop()

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f": {FAIL}" if FAIL else ""))
    raise SystemExit(1 if FAIL else 0)


def _els(root, name):
    return [el for el in root.iter() if el.tag.split("}")[-1] == name]


def _chart_one(kind, path):
    rc, out = run("chart", kind, path, "-o", os.path.join(WORK, kind + ".html"), "--title", kind)
    svg = os.path.join(WORK, kind + ".svg")
    if rc != 0 or not os.path.exists(svg):
        check(f"chart {kind}", False, out[-240:])
        return None
    rc2, out2 = run("audit", svg)
    check(f"chart {kind}", rc2 == 0, out2[-240:])
    return svg if rc2 == 0 else None


def charts():
    """Every taxonomy chart draws, audits, and keeps the caps that were promised."""
    import xml.etree.ElementTree as ET
    print("== chart types ==")
    csv_body = {
        "bubble": "x,y,size,group\n1,2,3,a\n2,3,8,a\n3,1,2,b\n",
        "beeswarm": "cat,val\nA,1\nA,1.2\nA,2\nB,3\nB,3.4\n",
        "step": "x,y,group\n1,2,a\n2,2,a\n3,4,a\n1,1,b\n2,3,b\n",
        "slope": "cat,a,b\nAlpha,2,5\nBeta,4,3\nGamma,1,1\n",
        "bump": "x,name,rank\nJan,A,1\nJan,B,2\nFeb,A,2\nFeb,B,1\n",
        "ridgeline": "group,val\nA,1\nA,1.2\nA,2\nA,2.4\nB,3\nB,3.2\nB,4\nB,3.5\n",
        "stack": "cat,group,val\nMon,read,2\nMon,write,1\nTue,read,3\nTue,write,2\n",
        "dumbbell": "cat,a,b\nAPI,10,40\nDB,20,25\n",
        "waterfall": "cat,val\nStart,10\nGain,4\nLoss,-2\nTotal,12\n",
        "histogram": "val\n1\n1.2\n2\n2.1\n3\n3.4\n4\n5\n",
        "box": "group,val\nA,1\nA,2\nA,2.2\nA,3\nA,9\nB,4\nB,4.5\nB,5\nB,5.2\n",
        "violin": "group,val\nA,1\nA,1.4\nA,2\nA,2.2\nA,3\nB,4\nB,4.2\nB,5\nB,5.5\nB,6\n",
        "strip": "group,val\nA,1\nA,2\nA,2.5\nB,4\nB,4.2\n",
        "pie": "cat,val\nA,4\nB,2\nC,1\n",
        "donut": "cat,val\nA,4\nB,2\nC,1\n",
        "waffle": "cat,val\nA,50\nB,30\nC,20\n",
        "treemap": "name,parent,val\nRoot,,0\nA,Root,3\nB,Root,1\nA1,A,2\n",
        "icicle": "name,parent,val\nRoot,,0\nA,Root,3\nB,Root,1\n",
        "sunburst": "name,parent,val\nRoot,,0\nA,Root,3\nB,Root,1\n",
        "heatmap": "x,y,val\na,a,1\na,b,3\nb,a,2\nb,b,4\n",
        "calendar": "date,val\n2026-01-05,1\n2026-01-06,3\n2026-01-12,2\n",
        "radar": "axis,series,val\nspeed,one,3\ncost,one,2\nrisk,one,4\nspeed,two,2\ncost,two,4\nrisk,two,1\n",
        "polar": "cat,val\nN,2\nE,4\nS,1\nW,3\n",
        "candle": "x,open,high,low,close\nMon,10,12,9,11\nTue,11,11,8,9\nWed,9,13,9,12\n",
        "status": "row,col,state\nweb,mon,ok\nweb,tue,warn\ndb,mon,down\ndb,tue,ok\n",
        "forest": "cat,est,lo,hi\nA,1.2,0.4,2.0\nB,-0.3,-1.1,0.4\n",
        "qq": "val\n1\n1.2\n2\n2.4\n3\n3.1\n4\n",
        "volcano": "x,y,label\n0.2,0.4,a\n1.5,0.001,b\n-1.4,0.01,c\n0.1,0.8,d\n",
        "sankey": "src,dst,val\na,b,3\na,c,1\nb,d,3\nc,d,1\n",
        "stream": "x,group,val\n1,a,2\n1,b,1\n2,a,3\n2,b,2\n3,a,2\n3,b,4\n",
        "funnel": "cat,val\nSee,100\nTry,40\nPay,10\n",
        "combo": "x,bar,line\nMon,2,0.2\nTue,4,0.5\nWed,3,0.4\n",
        "quadrant": "x,y,label\n1,2,A\n-1,3,B\n2,-1,C\n-2,-2,D\n",
        "contour": "x,y,z\n0,0,1\n1,0,2\n0,1,2\n1,1,4\n0.5,0.5,3\n",
        "heatgeo": "lat,lon,val\n52.4,-1.5,2\n52.5,-1.4,5\n53.4,-2.2,8\n53.5,-2.3,3\n",
        "od": "lon,lat,lon2,lat2,val\n-1.5,52.4,4.4,51.9,4\n-2.2,53.4,4.5,51.9,2\n",
        "cluster": "lat,lon\n52.40,-1.50\n52.41,-1.51\n52.42,-1.49\n53.48,-2.24\n",
    }
    json_body = {
        "dag": {"title": "Dag", "nodes": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}, {"id": "c", "name": "C"}],
                "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}]},
        "force": {"title": "Force", "nodes": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}, {"id": "c", "name": "C"}],
                  "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}, {"from": "a", "to": "c"}]},
        "radial": {"title": "Radial", "nodes": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}, {"id": "c", "name": "C"}],
                   "edges": [{"from": "a", "to": "b"}, {"from": "a", "to": "c"}]},
        "tree": {"title": "Tree", "nodes": [{"id": "a", "name": "A"}, {"id": "b", "name": "B", "parent": "a"},
                                             {"id": "c", "name": "C", "parent": "a"}, {"id": "d", "name": "D", "parent": "b"}]},
        "dtree": {"title": "Split", "nodes": [{"id": "a", "name": "A"}, {"id": "b", "name": "B", "parent": "a", "label": "yes"},
                                               {"id": "c", "name": "C", "parent": "a", "label": "no"}]},
        "nested": {"title": "Nest", "nodes": [{"id": "a", "name": "A"}, {"id": "b", "name": "B", "parent": "a"},
                                               {"id": "c", "name": "C", "parent": "a"}]},
        "kg": {"title": "KG", "nodes": [{"id": "a", "name": "A", "kind": "type"}, {"id": "b", "name": "B", "kind": "value"}],
               "edges": [{"from": "a", "to": "b"}]},
        "context": {"title": "Context", "nodes": [{"id": "u", "name": "User", "kind": "person"},
                                                   {"id": "s", "name": "System", "kind": "system", "focal": True}],
                    "edges": [{"from": "u", "to": "s", "label": "uses"}]},
        "uml": {"title": "Classes", "nodes": [{"id": "a", "name": "Animal", "attrs": ["age"], "methods": ["speak"]},
                                               {"id": "d", "name": "Dog", "attrs": ["breed"], "methods": ["bark"]}],
                "edges": [{"from": "d", "to": "a", "kind": "inherit"}]},
        "deploy": {"title": "Deploy", "zones": [{"id": "z", "name": "Edge", "nodes": [{"id": "a", "name": "Proxy"}, {"id": "b", "name": "Web"}]}]},
        "layers": {"title": "Layers", "layers": [{"name": "API", "sub": "http"}, {"name": "Core", "sub": "rules"}, {"name": "Store", "sub": "sql"}]},
        "integration": {"title": "Flow", "nodes": [{"id": "s", "name": "CRM", "col": "source"}, {"id": "c", "name": "Core", "col": "core"},
                                                    {"id": "k", "name": "App", "col": "consumer"}],
                        "edges": [{"from": "s", "to": "c", "label": "in"}, {"from": "c", "to": "k", "label": "out"}]},
        "current": {"title": "Now", "nodes": [{"id": "a", "name": "Billing", "group": "Finance"},
                                               {"id": "b", "name": "Ledger", "group": "Finance"},
                                               {"id": "c", "name": "Site", "group": "Web"}]},
        "er": {"title": "ER", "entities": [{"id": "u", "name": "User", "attrs": [{"name": "id", "key": "pk"}, {"name": "name"}]},
                                           {"id": "o", "name": "Order", "attrs": [{"name": "id", "key": "pk"}]}],
               "relations": [{"from": "u", "to": "o", "from_card": "1", "to_card": "*"}]},
        "wardley": {"title": "Wardley", "nodes": [{"id": "a", "name": "Compute", "visibility": 0.8, "evolution": 0.7},
                                                   {"id": "b", "name": "Custom app", "visibility": 0.4, "evolution": 0.2}],
                    "edges": [{"from": "b", "to": "a"}]},
        "swim": {"title": "Swim", "lanes": [{"id": "d", "name": "Dev"}, {"id": "r", "name": "Review"}],
                 "nodes": [{"id": "a", "name": "Write", "lane": "d"}, {"id": "b", "name": "Check", "lane": "r"}],
                 "edges": [{"from": "a", "to": "b"}]},
        "state": {"title": "State", "nodes": [{"id": "n", "name": "New"}, {"id": "p", "name": "Paid"}, {"id": "s", "name": "Shipped"}],
                  "edges": [{"from": "n", "to": "p", "label": "pay"}, {"from": "p", "to": "s", "label": "ship"},
                            {"from": "s", "to": "n", "label": "return"}]},
        "bpmn": {"title": "BPMN", "nodes": [{"id": "s", "name": "Start", "shape": "event"}, {"id": "t", "name": "Check", "shape": "task"},
                                             {"id": "g", "name": "OK", "shape": "gateway"}, {"id": "e", "name": "End", "shape": "event"}],
                 "edges": [{"from": "s", "to": "t"}, {"from": "t", "to": "g"}, {"from": "g", "to": "e", "label": "yes"}]},
        "fishbone": {"title": "Cause", "problem": "Latency", "ribs": [{"name": "Code", "causes": ["N+1", "lock"]},
                                                                      {"name": "Data", "causes": ["index"]}]},
        "flywheel": {"title": "Loop", "hub": "Trust", "nodes": [{"name": "Ship"}, {"name": "Learn"}, {"name": "Fix"}]},
        "kanban": {"title": "Board", "columns": [{"name": "Todo", "cards": [{"name": "Spec"}]},
                                                  {"name": "Doing", "cards": [{"name": "Draw", "blocked": True}]},
                                                  {"name": "Done", "cards": [{"name": "Ship"}]}]},
        "gantt": {"title": "Plan", "tasks": [{"name": "Design", "start": "2026-01-01", "end": "2026-01-10"},
                                              {"name": "Build", "start": "2026-01-08", "end": "2026-02-01"}]},
        "timeline": {"title": "Road", "events": [{"name": "Alpha", "at": "2026-01"}, {"name": "Beta", "at": "2026-03"},
                                                  {"name": "Live", "at": "2026-06"}]},
        "journey": {"title": "Journey", "stages": [{"name": "See", "score": 3, "note": "ad"},
                                                    {"name": "Try", "score": 4, "note": "trial"},
                                                    {"name": "Pay", "score": 2, "note": "price"}]},
        "story": {"title": "Map", "backbone": ["Browse", "Buy"],
                  "releases": [{"name": "R1", "stories": ["Search", "Cart"]}, {"name": "R2", "stories": ["Pay"]}]},
        "org": {"title": "Org", "nodes": [{"id": "a", "name": "Lead", "sub": "eng"}, {"id": "b", "name": "A", "parent": "a", "sub": "api"},
                                           {"id": "c", "name": "B", "parent": "a", "sub": "web"}]},
        "math": {"title": "Sine", "xmin": -6.28, "xmax": 6.28, "ymin": -1.5, "ymax": 1.5,
                 "equations": ["y = sin(x)"]},
        "venn": {"title": "Overlap", "sets": [{"name": "A", "size": 20}, {"name": "B", "size": 16}], "overlap": 6},
        "choropleth": {"type": "FeatureCollection", "title": "Regions", "features": [
            {"type": "Feature", "properties": {"name": "West", "value": 2},
             "geometry": {"type": "Polygon", "coordinates": [[[-1.6, 52.3], [-1.2, 52.3], [-1.2, 52.6], [-1.6, 52.6], [-1.6, 52.3]]]}},
            {"type": "Feature", "properties": {"name": "North", "value": 8},
             "geometry": {"type": "Polygon", "coordinates": [[[-2.4, 53.3], [-2.0, 53.3], [-2.0, 53.6], [-2.4, 53.6], [-2.4, 53.3]]]}}]},
    }
    drawn = {}
    for kind, body in csv_body.items():
        path = os.path.join(WORK, kind + ".csv")
        open(path, "w", encoding="utf-8").write(body)
        drawn[kind] = _chart_one(kind, path)
    for kind, spec in json_body.items():
        path = os.path.join(WORK, kind + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(spec, f)
        drawn[kind] = _chart_one(kind, path)
    for kind, path in (
        ("container", os.path.join(HERE, "examples", "arch.json")),
        ("component", os.path.join(HERE, "examples", "arch.json")),
        ("process", os.path.join(HERE, "examples", "seq_checkout.json")),
        ("flowsheet", os.path.join(HERE, "examples", "flow_decision.json")),
        ("decision", os.path.join(HERE, "examples", "flow_decision.json")),
        ("point", os.path.join(HERE, "examples", "geo_cities.csv")),
    ):
        rc, out = run("chart", kind, path, "-o", os.path.join(WORK, "alias-" + kind + ".html"))
        svg = os.path.join(WORK, "alias-" + kind + ".svg")
        if rc != 0 or not os.path.exists(svg):
            check(f"chart alias {kind}", False, out[-240:])
            continue
        rc2, out2 = run("audit", svg)
        check(f"chart alias {kind}", rc2 == 0, out2[-240:])
    rc, out = run("chart", "terrain", "x", "-o", os.path.join(WORK, "no.html"))
    check("terrain refused", rc != 0 and "DEM" in out, out[-200:])
    rc, out = run("chart", "print", "x", "-o", os.path.join(WORK, "no.html"))
    check("print refused", rc != 0 and "pdf" in out, out[-200:])
    rc, out = run("validate", os.path.join(WORK, "heatmap.csv"), "--type", "heatmap")
    check("validate heatmap", rc == 0, out[-200:])
    rc, out = run("describe", "heatmap")
    check("describe heatmap", rc == 0 and "Cell color follows val" in out, out[-160:])
    rc, out = run("export", os.path.join(WORK, "heatmap"), "--to", "svg", "-o", os.path.join(WORK, "heatmap-ex.svg"))
    check("chart export round-trip", rc == 0 and os.path.exists(os.path.join(WORK, "heatmap-ex.svg")), out[-200:])
    pie = os.path.join(WORK, "pie9.csv")
    open(pie, "w", encoding="utf-8").write("cat,val\n" + "".join(f"S{i},{i + 1}\n" for i in range(9)))
    rc, out = run("chart", "pie", pie, "-o", os.path.join(WORK, "pie9.html"), "--title", "Pie")
    check("pie of 9 refused", rc != 0 and "slices" in out, out[-200:])
    rc, out = run("chart", "pie", pie, "-o", os.path.join(WORK, "pie9.html"), "--title", "Pie", "--no-budget")
    check("pie --no-budget draws", rc == 0, out[-200:])
    if drawn.get("state"):
        root = ET.parse(drawn["state"]).getroot()
        ship = [el for el in _els(root, "text") if (el.text or "") == "Shipped"]
        circs = _els(root, "circle")
        ok = False
        if ship and circs:
            circ = min(circs, key=lambda c: abs(float(c.get("cx")) - float(ship[0].get("x"))))
            ok = float(ship[0].get("y")) > float(circ.get("cy")) + float(circ.get("r"))
        check("state label sits under the circle", ok)
    if drawn.get("sankey"):
        root = ET.parse(drawn["sankey"]).getroot()
        bars = [el for el in _els(root, "rect") if el.get("width") == "12"]
        labels = {el.text: el for el in _els(root, "text") if (el.text or "") in ("a", "b", "c", "d")}
        ribbons = [el for el in _els(root, "path") if (el.get("d") or "").rstrip().endswith("Z")]
        ok = len(bars) == 4 and set(labels) == {"a", "b", "c", "d"} and len(ribbons) == 4
        ax = float(labels["a"].get("x"))
        ok = ok and any(float(b.get("x")) > ax + 4 for b in bars)
        dx = float(labels["d"].get("x"))
        ok = ok and any(float(b.get("x")) + 12 < dx - 4 for b in bars)
        for name in ("b", "c"):
            lab = labels[name]
            lx, ly = float(lab.get("x")), float(lab.get("y"))
            near = [b for b in bars if abs(float(b.get("x")) + 6 - lx) < 4]
            if not near:
                ok = False
                continue
            bar = min(near, key=lambda b: abs(float(b.get("y")) + float(b.get("height")) / 2 - ly))
            mid = float(bar.get("y")) + float(bar.get("height")) / 2
            if abs(ly - (mid + 4)) > 2:
                ok = False
        for el in ribbons:
            nums = [float(v) for v in __import__("re").findall(r"-?\d+\.?\d*", el.get("d"))]
            if len(nums) < 12 or abs(nums[1] - nums[3]) > 0.2 or abs(nums[9] - nums[11]) > 0.2:
                ok = False
        check("sankey ribbons meet the bars", ok)
    if drawn.get("heatmap"):
        root = ET.parse(drawn["heatmap"]).getroot()
        cells = [el for el in _els(root, "text") if el.get("text-anchor") == "middle" and (el.text or "") in ("1", "4")]
        got = {el.text: el.get("fill") for el in cells}
        check("heatmap text contrasts with the cell", got.get("1") == "#2d3142" and got.get("4") == "#ffffff", str(got))
    if drawn.get("org"):
        root = ET.parse(drawn["org"]).getroot()
        boxes = [el for el in _els(root, "rect") if el.get("width") == "156"]
        left = min(float(el.get("x")) for el in boxes) if boxes else -1
        check("org boxes stay on the canvas", left >= 16, str(left))
    slope = os.path.join(WORK, "math-slope.json")
    with open(slope, "w", encoding="utf-8") as f:
        json.dump({"title": "Slope", "xmin": 0, "xmax": 2, "ymin": 0, "ymax": 2, "equal": True,
                   "equations": ["y = x"]}, f)
    rc, out = run("chart", "math", slope, "-o", os.path.join(WORK, "math-slope.html"))
    ok = False
    if rc == 0:
        root = ET.parse(os.path.join(WORK, "math-slope.svg")).getroot()
        paths = [el for el in _els(root, "path") if el.get("stroke") == "#0072B2"]
        if paths:
            nums = [float(v) for v in __import__("re").findall(r"-?\d+\.?\d*", paths[0].get("d"))]
            if len(nums) >= 4:
                x1, y1, x2, y2 = nums[0], nums[1], nums[-2], nums[-1]
                ok = x2 > x1 + 30 and y2 < y1 - 30 and abs((x2 - x1) - (y1 - y2)) < 12
    check("math y=x climbs at equal scale", ok)
    pole = os.path.join(WORK, "math-pole.json")
    with open(pole, "w", encoding="utf-8") as f:
        json.dump({"title": "Pole", "xmin": -2, "xmax": 2, "ymin": -4, "ymax": 4,
                   "equations": ["y = 1/x"]}, f)
    rc, out = run("chart", "math", pole, "-o", os.path.join(WORK, "math-pole.html"))
    ok = False
    if rc == 0:
        root = ET.parse(os.path.join(WORK, "math-pole.svg")).getroot()
        axis = [el for el in _els(root, "line") if el.get("x1") == el.get("x2") and el.get("stroke-width") == "1.3"]
        paths = [el for el in _els(root, "path") if el.get("stroke") == "#0072B2"]
        if axis and len(paths) >= 2:
            vx = float(axis[0].get("x1"))
            ok = True
            for el in paths:
                xs = [float(v) for v in __import__("re").findall(r"-?\d+\.?\d*", el.get("d"))][0::2]
                if not xs or not (all(x < vx - 4 for x in xs) or all(x > vx + 4 for x in xs)):
                    ok = False
    check("math 1/x breaks at the asymptote", ok)
    rc, out = run("describe", "math")
    check("describe math", rc == 0 and "base 10" in out, out[-180:])
    bad = os.path.join(WORK, "math-bad.json")
    with open(bad, "w", encoding="utf-8") as f:
        json.dump({"equations": ["y = sin("]}, f)
    rc, out = run("validate", bad, "--type", "math")
    check("math rejects a broken equation", rc != 0 and "cannot read" in out, out[-180:])
    many = os.path.join(WORK, "math-many.json")
    with open(many, "w", encoding="utf-8") as f:
        json.dump({"equations": [f"y = x+{i}" for i in range(9)], "xmin": -1, "xmax": 1}, f)
    rc, out = run("chart", "math", many, "-o", os.path.join(WORK, "math-many.html"), "--title", "Many")
    check("math of 9 refused", rc != 0 and "equations" in out, out[-180:])
    rc, out = run("chart", "math", many, "-o", os.path.join(WORK, "math-many.html"), "--title", "Many", "--no-budget")
    check("math --no-budget draws", rc == 0, out[-180:])


def agent_loop():
    """What an agent relies on: one command, JSON out, no tracebacks, an audit that sees overlaps."""
    import xml.etree.ElementTree as ET
    print("== agent loop ==")
    flow = os.path.join(WORK, "loop.json")
    with open(flow, "w", encoding="utf-8") as f:
        json.dump({"title": "Loop", "nodes": [{"id": "a", "name": "Start", "shape": "oval"},
                                              {"id": "b", "name": "Check", "shape": "diamond"},
                                              {"id": "c", "name": "Done", "shape": "oval"}],
                   "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c", "label": "yes"}]}, f)
    rc, out = run("flow", flow, "-o", os.path.join(WORK, "loop.html"))
    try:
        rep = json.loads(out)
    except ValueError:
        rep = {}
    check("render prints one JSON verdict", rc == 0 and rep.get("ok") is True and rep.get("svg", "").endswith(".svg"), out[:200])
    rc, out = run("flow", flow, "-o", os.path.join(WORK, "loop-svg.svg"))
    with open(os.path.join(WORK, "loop-svg.svg"), encoding="utf-8") as f:
        head = f.read(5)
    check("-o NAME.svg writes the SVG there and the page beside it",
          rc == 0 and head == "<svg " and os.path.exists(os.path.join(WORK, "loop-svg.html")), out[:200])
    root = ET.parse(os.path.join(WORK, "loop.svg")).getroot()
    rx = [r.get("rx") for r in _els(root, "rect") if r.get("width") == "160"]
    check("oval start and end are drawn round", rx.count("20") >= 4, str(rx))

    junk = {"list.json": "[1, 2, 3]", "nodes_str.json": '{"nodes": "abc"}', "noid.json": '{"nodes": [{"name": "A"}]}',
            "broken.json": '{"nodes": [', "seq_in_flow.json": '{"actors": [{"id": "a"}], "messages": []}'}
    clean = True
    for name, body in junk.items():
        path = os.path.join(WORK, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        for cmd in ("flow", "seq", "validate"):
            if cmd != "flow" and name == "seq_in_flow.json":
                continue  # a valid, empty sequence: only flow should refuse it
            argv = [cmd, path] + (["-o", os.path.join(WORK, "junk.html")] if cmd != "validate" else [])
            rc, out = run(*argv)
            if rc == 0 or "Traceback" in out or '"fix"' not in out:
                clean = False
                print("     ", cmd, name, out[:160])
    check("malformed specs get a fix, not a traceback", clean)
    nan = os.path.join(WORK, "nan.csv")
    with open(nan, "w", encoding="utf-8") as f:
        f.write("a,b\n1,nan\n2,inf\n")
    rc, out = run("scatter", nan, "--x", "a", "--y", "b", "-o", os.path.join(WORK, "nan.html"))
    check("nan values are refused before drawing", rc == 1 and '"stage": "validate"' in out, out[:200])

    mixed = os.path.join(WORK, "mixed.json")
    nodes = [{"id": i, "name": n, "shape": "rect"} for i, n in
             (("in", "Ticket"), ("sev", "Sev1?"), ("page", "Page"), ("known", "Known?"),
              ("kb", "Reply"), ("q", "Queue"), ("mit", "Mitigate"), ("fix", "Fix"), ("pm", "Review"), ("out", "Close"))]
    for n in nodes:
        if n["id"] in ("sev", "known"):
            n["shape"] = "diamond"
        if n["id"] in ("page", "mit", "pm"):
            n["lane"] = 1
    pairs = [("in", "sev"), ("sev", "page"), ("sev", "known"), ("page", "mit"), ("mit", "pm"), ("pm", "out"),
             ("known", "kb"), ("known", "q"), ("q", "fix"), ("kb", "out"), ("fix", "out")]
    edges = [dict({"from": a, "to": b}, **({"label": "x"} if a in ("sev", "known") else {})) for a, b in pairs]
    with open(mixed, "w", encoding="utf-8") as f:
        json.dump({"title": "Mixed lanes", "budget": False, "nodes": nodes, "edges": edges}, f)
    rc, out = run("flow", mixed, "-o", os.path.join(WORK, "mixed.html"))
    check("lane on some nodes in a row does not stack the rest", rc == 0, out[:300])

    def svg_file(name, body):
        path = os.path.join(WORK, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300"><title>t</title><desc>d</desc>'
                    '<defs><marker id="m"><path d="M0,0 L6,3 L0,6"/></marker></defs>' + body + "</svg>")
        return path
    rc, out = run("audit", svg_file("collide.svg", '<text x="50" y="50" font-size="12">Overlapping label</text>'
                                                   '<text x="60" y="52" font-size="12">Another label</text>'))
    check("audit catches labels on labels", rc == 1 and "collide" in out, out[:200])
    rc, out = run("audit", svg_file("through.svg", '<rect x="150" y="100" width="100" height="50" fill="#fff" stroke="#000"/>'
                                                   '<path d="M100,125 L300,125" stroke="#000" marker-end="url(#m)"/>'))
    check("audit catches an arrow through a box", rc == 1 and "through" in out, out[:200])
    rc, out = run("audit", svg_file("spill.svg", '<rect x="100" y="100" width="60" height="40" fill="#fff" stroke="#000"/>'
                                                 '<text x="130" y="124" font-size="12" text-anchor="middle">A label far too long for this box</text>'))
    check("audit catches a label wider than its box", rc == 1 and "spill" in out, out[:200])
    rc, out = run("audit", svg_file("rotated.svg", '<text transform="translate(24 150) rotate(-90)" font-size="12" '
                                                   'text-anchor="middle">Signups per month</text>'
                                                   '<text x="200" y="20" font-size="12" text-anchor="middle">Title</text>'))
    check("audit reads transforms (rotated axis title is fine)", rc == 0, out[:200])

    far = os.path.join(WORK, "far")
    os.makedirs(far, exist_ok=True)
    p = subprocess.run([sys.executable, GRAPH, "export", os.path.join(WORK, "loop"), "--to", "svg",
                        "-o", os.path.join(far, "loop.svg")], capture_output=True, text=True, cwd=far)
    check("export works from another directory", p.returncode == 0, (p.stdout + p.stderr)[:200])

    out_html = os.path.join(WORK, "mcp-inline.html")
    rs = mcp(['{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}',
              '{"jsonrpc":"2.0","method":"notifications/initialized"}',
              '{"jsonrpc":"2.0","id":2,"method":"ping"}',
              '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"render","arguments":{"type":"scatter"}}}',
              json.dumps({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "render", "arguments": {
                  "type": "bar", "out": out_html, "data": "svc,p99\napi,120\ndb,45\n",
                  "options": {"cat": "svc", "val": "p99", "title": "Latency"}}}})])
    ids = [r.get("id") for r in rs]
    check("mcp answers requests and never notifications", ids == [1, 2, 3, 4], str(ids))
    check("mcp ping", len(rs) > 1 and rs[1].get("result") == {})
    check("mcp bad call is an error, not a dead server", len(rs) > 3 and rs[2]["result"].get("isError") is True)
    text = rs[3]["result"]["content"][0]["text"] if len(rs) > 3 else ""
    check("mcp render takes inline CSV", '"ok": true' in text and os.path.exists(out_html), text[:200])

    print("== wrap, groups, mermaid ==")
    wrap = os.path.join(WORK, "wrap.json")
    with open(wrap, "w", encoding="utf-8") as f:
        json.dump({"title": "Wrap", "nodes": [
            {"id": "a", "name": "Ticket arrives from the customer portal", "shape": "oval"},
            {"id": "b", "name": "Is this a severity one incident?", "shape": "diamond"},
            {"id": "c", "name": "Reply with the help-center article", "sub": "send the link with a short note"}],
            "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c", "label": "no"}]}, f)
    rc, out = run("flow", wrap, "-o", os.path.join(WORK, "wrap.svg"))
    body = open(os.path.join(WORK, "wrap.svg"), encoding="utf-8").read() if rc == 0 else ""
    check("long names wrap inside their box and pass the audit", rc == 0 and "incident?" in body and "..." not in body, out[:200])
    grp = os.path.join(WORK, "groups.json")
    with open(grp, "w", encoding="utf-8") as f:
        json.dump({"title": "Groups", "budget": False,
                   "nodes": [{"id": "w", "name": "Web", "layer": 0}, {"id": "m", "name": "Mobile", "layer": 0},
                             {"id": "g", "name": "Gateway", "layer": 1},
                             {"id": "o", "name": "Orders", "layer": 2}, {"id": "p", "name": "Payments", "layer": 2},
                             {"id": "s", "name": "Stripe", "layer": 3}, {"id": "db", "name": "Postgres", "layer": 3}],
                   "edges": [{"from": "w", "to": "g"}, {"from": "m", "to": "g"}, {"from": "g", "to": "o"},
                             {"from": "o", "to": "p"}, {"from": "p", "to": "s"}, {"from": "o", "to": "db"}],
                   "groups": [{"id": "core", "name": "Core", "nodes": ["o", "p", "db"]}]}, f)
    rc, out = run("arch", grp, "-o", os.path.join(WORK, "groups.svg"))
    body = open(os.path.join(WORK, "groups.svg"), encoding="utf-8").read() if rc == 0 else ""
    check("a group draws one frame holding only its members", rc == 0 and body.count('data-group="core"') == 1, out[:200])
    mm = {"flow.mmd": "---\ntitle: Loop\n---\nflowchart TD\n  A([Start]) --> B{OK?}\n  B -->|no| C[Fix]\n  C -.-> A\n"
                      "  B ==>|yes| D([Done])\n  subgraph g [Group]\n    C\n  end\n",
          "seq.mmd": "sequenceDiagram\n  actor U as User\n  participant S as Server\n  U->>S: request\n  Note over U,S: x\n  S-->>U: reply\n",
          "er.mmd": "erDiagram\n  CUSTOMER ||--o{ ORDER : places\n  ORDER {\n    uuid id PK\n  }\n"}
    for name, text in mm.items():
        path = os.path.join(WORK, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        rc, out = run("mermaid", path, "-o", os.path.join(WORK, name.replace(".mmd", "-mm.svg")))
        check(f"mermaid {name.split('.')[0]} renders and passes the audit", rc == 0 and '"ok": true' in out, out[:240])
    rc, out = run("mermaid", os.path.join(WORK, "flow.mmd"), "-o", os.path.join(WORK, "flow-mm.svg"))
    try:
        lay = json.loads(out).get("layout") or []
    except ValueError:
        lay = []
    check("render reply outlines the layout", bool(lay) and lay[0] == "row 1: Start" and any("(decision)" in r for r in lay)
          and any(r.startswith("frame Group:") for r in lay), str(lay))
    flow_svg = os.path.join(WORK, "flow-mm.svg")
    if os.path.exists(flow_svg):
        root = ET.parse(flow_svg).getroot()
        tops = sorted((float(r.get("y")), r.get("data-node")) for r in _els(root, "rect") if r.get("data-node"))
        check("a loop's start stays on top", bool(tops) and tops[0][1] == "A", str(tops[:2]))
    rc, out = run("export", os.path.join(WORK, "flow-mm"), "--to", "drawio")
    ok = rc == 0 and os.path.exists(os.path.join(WORK, "flow-mm.drawio"))
    if ok:
        xml_root = ET.parse(os.path.join(WORK, "flow-mm.drawio")).getroot()
        edges = [c for c in xml_root.iter("mxCell") if c.get("edge") == "1"]
        ok = len(edges) >= 4 and all(c.get("source") and c.get("target") for c in edges)
    check("draw.io export keeps boxes and attached arrows", ok, out[:200])
    rc, out = run("export", os.path.join(WORK, "flow-mm"), "--to", "excalidraw")
    scene = json.load(open(os.path.join(WORK, "flow-mm.excalidraw"), encoding="utf-8")) if rc == 0 else {}
    arrows = [e for e in scene.get("elements", []) if e.get("type") == "arrow"]
    check("excalidraw export binds arrows to shapes",
          bool(arrows) and all(a.get("startBinding") and a.get("endBinding") for a in arrows), out[:200])
    ic = os.path.join(WORK, "icons.mmd")
    with open(ic, "w", encoding="utf-8") as f:
        f.write("flowchart TD\n  U[fa:fa-user Customer] --> D[(fa:fa-database Orders DB)]\n")
    rc, out = run("mermaid", ic, "-o", os.path.join(WORK, "icons-mm.svg"))
    body = open(os.path.join(WORK, "icons-mm.svg"), encoding="utf-8").read() if rc == 0 else ""
    check("mermaid fa: icons draw as glyphs and leave the label clean",
          rc == 0 and body.count('stroke-linejoin="round"') >= 2 and "fa:fa" not in body and ">Customer<" in body, out[:200])
    broken = os.path.join(WORK, "broken.mmd")
    with open(broken, "w", encoding="utf-8") as f:
        f.write("flowchart TD\n  A[Start --> B\n")
    rc, out = run("mermaid", broken, "-o", os.path.join(WORK, "broken.svg"))
    check("broken mermaid names the line and the fix", rc == 1 and "line 2" in out and '"fix"' in out, out[:200])

    with open(os.path.join(HERE, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
        plugin_v = json.load(f)["version"]
    rc, out = run("--version")
    check("plugin.json version matches graph.py", plugin_v in out, f"{plugin_v} vs {out.strip()}")


if __name__ == "__main__":
    main()
