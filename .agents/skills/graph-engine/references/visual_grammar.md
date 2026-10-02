# visual_grammar.md — taste & budgets (enforced by validate + audit)

## Color semantics (never decorative)

| token | hex | use |
|---|---|---|
| paper / ink / muted | `#f5f5f5` / `#2d3142` / `#4f5d75` | ground, text, arrows |
| accent (coral) | `#eb6c36` | 1–2 focal elements max per diagram |
| link (blue) | `#2e5aa8` | HTTP/API arrows, FK badges |
| series | Okabe-Ito | groups/series only, never architecture |

## Shape grammar (shape carries type, never color)

oval=start/end · rect=step · diamond=decision (≤3 exits, nest beyond) · dot=merge ·
lifeline dashed=sequence actor · table header=entity, bold=PK, blue badge=FK.

## Typography

One system font on the figure (`system-ui, Segoe UI, sans-serif`).
Title and subtitle are drawn on the diagram. Gridlines, markers, and
highlighted points are flags on bar, line, scatter, and geo.
No display serif, no tracked-out eyebrows, no `Fig. N` label on the drawing.
Units in parens, source line, and `n` stay on the figure.

## Hard budgets (validate=error, audit=warning)

nodes 9 · edges 12 · focal 2 · diamond exits 3 · seq actors 6 / msgs 16 ·
schema tables 6 / cols-shown 12 warn · bars 24 / cats 12 · scatter pts 400.
Over → split (overview+detail, sub-sequences, bounded contexts, top-N+Other).

## Connectors

Orthogonal elbows only (r=8). Labels masked with 6px gap, ≤14 chars uppercase.
No shared attach points (≥12px fan). No line behind a non-endpoint box
(dashed if unavoidable). Ratio data never shows a negative axis.
